#!/usr/bin/env python3
"""Combine pero-ocr PAGE XML (text lines) with TextBite YOLO regions and derive
page structure: columns, blocks, paragraphs, lines and reading order.

Hierarchy in the output JSON:
    page -> columns (geometric)
         -> blocks (YOLO title/text regions, or clusters of lines YOLO missed)
              -> paragraphs -> lines

Reading order of blocks: recursive XY-cut; vertical cuts at detected column
gutters are preferred (tolerant to small overlaps), then other vertical gaps,
then horizontal cuts.  Horizontal rules spanning >= 2 columns (detect_rules.py)
either open a section read after the rest (e.g. feuilleton), act as local
separators, or are ignored -- chosen per rule by a word-division (hyphenation)
score of the resulting order.  Paragraphs are finally linked across blocks,
columns and pages (hyphen + lowercase, or full last line + unindented start).
"""
import argparse
import json
import re
import statistics as st
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"p": "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"}


# ---------------------------------------------------------------- geometry
def pts(s):
    return [tuple(int(float(v)) for v in p.split(",")) for p in s.split()]


def bbox_of(points):
    xs, ys = zip(*points)
    return [min(xs), min(ys), max(xs), max(ys)]


def union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def inter_area(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0


def area(b):
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


# ---------------------------------------------------------------- input
def read_page_xml(path):
    root = ET.parse(path).getroot()
    page = root.find("p:Page", NS)
    w, h = int(page.get("imageWidth")), int(page.get("imageHeight"))
    lines = []
    for reg in page.iter(f"{{{NS['p']}}}TextRegion"):
        for tl in reg.findall("p:TextLine", NS):
            coords = pts(tl.find("p:Coords", NS).get("points"))
            bl_el = tl.find("p:Baseline", NS)
            baseline = pts(bl_el.get("points")) if bl_el is not None else None
            te = tl.find("p:TextEquiv", NS)
            text = te.findtext("p:Unicode", default="", namespaces=NS) if te is not None else ""
            conf = float(te.get("conf", 0)) if te is not None and te.get("conf") else None
            box = bbox_of(coords)
            lines.append({
                "id": tl.get("id"), "pero_region": reg.get("id"),
                "bbox": box, "polygon": coords, "baseline": baseline,
                "baseline_y": st.mean(p[1] for p in baseline) if baseline else box[3],
                "text": text.strip(), "conf": conf,
            })
    return w, h, lines


def is_noise(line, width, pitch):
    t = re.sub(r"\s", "", line["text"])
    x0, _, x1, _ = line["bbox"]
    if x1 - x0 < 3 * pitch and (x1 < 0.03 * width or x0 > 0.97 * width):
        return True  # specks on the scan border
    return len(t) == 0 or (len(t) <= 2 and not t.isalnum()) or (line["conf"] is not None and line["conf"] < 0.3 and len(t) <= 4)


# ---------------------------------------------------------------- blocks
def build_blocks(lines, regions, pitch):
    """Assign lines to YOLO regions; cluster the rest into fallback blocks."""
    assigned = {i: [] for i in range(len(regions))}
    rest = []
    for ln in lines:
        la = area(ln["bbox"]) or 1
        best, best_v = None, 0.0
        for i, r in enumerate(regions):
            v = inter_area(ln["bbox"], r["bbox"]) / la
            # prefer text regions for whole lines; titles win only if they cover the line
            if r["cls"] == "title" and inter_area(ln["bbox"], r["bbox"]) / (area(r["bbox"]) or 1) < 0.5:
                v *= 0.5
            if v > best_v:
                best, best_v = i, v
        if best is not None and best_v >= 0.5:
            assigned[best].append(ln)
        else:
            rest.append(ln)

    blocks = []
    runin = []  # title boxes that captured no line -> run-in headings
    for i, r in enumerate(regions):
        if assigned[i]:
            blocks.append({"type": r["cls"], "source": "yolo", "yolo_conf": r["conf"],
                           "yolo_bbox": r["bbox"], "lines": assigned[i]})
        elif r["cls"] == "title":
            runin.append(r["bbox"])

    # union-find clustering of unassigned lines (vertical neighbours with x-overlap)
    parent = list(range(len(rest)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, a in enumerate(rest):
        for j in range(i + 1, len(rest)):
            b = rest[j]["bbox"]
            ab = a["bbox"]
            xo = min(ab[2], b[2]) - max(ab[0], b[0])
            minw = min(ab[2] - ab[0], b[2] - b[0])
            gap = max(b[1] - ab[3], ab[1] - b[3])
            if xo > 0.5 * minw and gap < 0.8 * pitch:
                parent[find(i)] = find(j)
    groups = {}
    for i, ln in enumerate(rest):
        groups.setdefault(find(i), []).append(ln)
    for g in groups.values():
        hs = [ln["bbox"][3] - ln["bbox"][1] for ln in g]
        # large type without YOLO region -> treat as title
        typ = "title" if st.median(hs) > 1.8 * pitch and len(g) <= 3 else "text"
        blocks.append({"type": typ, "source": "cluster", "lines": g})

    for b in blocks:
        b["lines"].sort(key=lambda l: (l["baseline_y"], l["bbox"][0]))
        b["bbox"] = union([l["bbox"] for l in b["lines"]])

    # overlapping YOLO boxes (nested low-confidence boxes) and lines YOLO missed
    # inside a block produce text blocks whose lines interleave -> merge them
    def interleaved(a, b):
        xa, xb = a["bbox"], b["bbox"]
        xo = min(xa[2], xb[2]) - max(xa[0], xb[0])
        yo = min(xa[3], xb[3]) - max(xa[1], xb[1])
        return xo > 0.5 * min(xa[2] - xa[0], xb[2] - xb[0]) and yo > 0.8 * pitch

    changed = True
    while changed:
        changed = False
        for i, a in enumerate(blocks):
            for b in blocks[i + 1:]:
                if a["type"] == b["type"] == "text" and interleaved(a, b):
                    a["lines"] = sorted(a["lines"] + b["lines"], key=lambda l: (l["baseline_y"], l["bbox"][0]))
                    a["bbox"] = union([l["bbox"] for l in a["lines"]])
                    if b["source"] == "yolo":
                        a["source"] = "yolo"
                    blocks.remove(b)
                    changed = True
                    break
            if changed:
                break
    return blocks, runin


# ---------------------------------------------------------------- reading order
def split_axis(items, axis, tol, min_gap):
    """Split items (bbox at it['bbox']) into groups separated by gaps along axis."""
    lo, hi = (0, 2) if axis == 0 else (1, 3)
    its = sorted(items, key=lambda it: it["bbox"][lo])
    groups, cur, cur_end = [], [], None
    for it in its:
        s, e = it["bbox"][lo] + tol, it["bbox"][hi] - tol
        if e < s:
            s = e = (it["bbox"][lo] + it["bbox"][hi]) / 2
        if cur and s > cur_end + min_gap:
            groups.append(cur)
            cur, cur_end = [], None
        cur.append(it)
        cur_end = e if cur_end is None else max(cur_end, e)
    if cur:
        groups.append(cur)
    return groups


def gutter_split(items, gutters, tol):
    """Split at column gutters that no item crosses by more than tol on both sides."""
    valid = [g for g in gutters
             if not any(it["bbox"][0] < g - tol and it["bbox"][2] > g + tol for it in items)]
    if not valid:
        return [items]
    groups = {}
    for it in items:
        cx = (it["bbox"][0] + it["bbox"][2]) / 2
        groups.setdefault(sum(cx > g for g in valid), []).append(it)
    return [groups[k] for k in sorted(groups)]


def xycut(items, pitch, gutters=()):
    if len(items) <= 1:
        return list(items)
    # running header row (e.g. "Strana 2. | MORAVSKÁ ORLICE | V Brně ..."):
    # a short top band of several small items is read first, before columns
    bands = split_axis(items, 1, tol=0.15 * pitch, min_gap=0.0)
    top = bands[0]
    if (len(bands) > 1 and len(top) >= 2
            and max(it["bbox"][3] for it in top) - min(it["bbox"][1] for it in top) <= 2.5 * pitch):
        rest = [it for b in bands[1:] for it in b]
        return sorted(top, key=lambda it: it["bbox"][0]) + xycut(rest, pitch, gutters)
    g = gutter_split(items, gutters, tol=2 * pitch)                    # detected columns
    if len(g) > 1:
        return [x for grp in g for x in xycut(grp, pitch, gutters)]
    g = split_axis(items, 0, tol=0.3 * pitch, min_gap=0.1 * pitch)     # other vertical gaps
    if len(g) > 1:
        return [x for grp in g for x in xycut(grp, pitch, gutters)]
    g = split_axis(items, 1, tol=0.15 * pitch, min_gap=0.0)            # rows
    if len(g) > 1:
        # a horizontal gap is a real separator only next to a band that spans
        # several columns; consecutive column-only bands are merged so that text
        # keeps flowing down each column across coincidental gaps
        crosses = lambda it: any(it["bbox"][0] < c - 2 * pitch and it["bbox"][2] > c + 2 * pitch
                                 for c in gutters)
        merged = []
        for grp in g:
            spanning = any(crosses(it) for it in grp)
            if merged and not spanning and not merged[-1][1]:
                merged[-1][0].extend(grp)
            else:
                merged.append([list(grp), spanning])
        if len(merged) > 1:
            g = [m[0] for m in merged]
        return [x for grp in g for x in xycut(grp, pitch, gutters)]
    return sorted(items, key=lambda it: (it["bbox"][1], it["bbox"][0]))


# ---------------------------------------------------------------- columns
def detect_columns(lines, width, height):
    narrow = [l for l in lines if (l["bbox"][2] - l["bbox"][0]) < 0.55 * width]
    if not narrow:
        return []
    cov = [0] * (width + 1)
    for l in narrow:
        for x in range(max(0, l["bbox"][0]), min(width, l["bbox"][2])):
            cov[x] += 1
    # gutters = pronounced valleys of the coverage profile; on skewed / curved
    # scans line boxes leak into the gutters, so valleys need not reach zero
    thr = 0.2 * max(cov)
    win, reach = int(0.04 * width), int(0.15 * width)
    xs = [x for x, c in enumerate(cov) if c > thr]
    lo, hi = (xs[0], xs[-1]) if xs else (0, width)
    gutters = []
    for x in range(lo + win, hi - win):
        c = cov[x]
        if c != min(cov[x - win:x + win + 1]):
            continue
        left, right = max(cov[max(0, x - reach):x]), max(cov[x + 1:x + reach + 1])
        if c < 0.65 * min(left, right) and (not gutters or x - gutters[-1] > 2 * win):
            gutters.append(x)
    edges = [lo] + gutters + [hi]
    runs = [[a, b] for a, b in zip(edges, edges[1:]) if b - a > 0.05 * width]
    cols = []
    for i, (x0, x1) in enumerate(runs):
        members = [l for l in narrow if x0 <= (l["bbox"][0] + l["bbox"][2]) / 2 < x1
                   and l["bbox"][2] - l["bbox"][0] < 1.25 * (x1 - x0)]
        if not members:
            continue
        # refine extent with robust percentiles of member lines
        lefts = sorted(l["bbox"][0] for l in members)
        rights = sorted(l["bbox"][2] for l in members)
        ys0 = sorted(l["bbox"][1] for l in members)
        ys1 = sorted(l["bbox"][3] for l in members)
        q = lambda a, p: a[min(len(a) - 1, int(p * len(a)))]
        cols.append({"id": f"c{len(cols) + 1}", "x0": max(x0 - 0.02 * width, q(lefts, 0.05)),
                     "x1": min(x1 + 0.02 * width, q(rights, 0.95)),
                     "y0": q(ys0, 0.02), "y1": q(ys1, 0.98), "n_lines": len(members),
                     "run": [x0, x1]})
    return cols


def column_gutters(cols):
    """Gutter positions = profile valleys between neighbouring columns."""
    return [a["run"][1] for a in cols[:-1]]


def block_columns(b, cols):
    out = []
    bw = b["bbox"][2] - b["bbox"][0]
    for c in cols:
        ov = min(b["bbox"][2], c["x1"]) - max(b["bbox"][0], c["x0"])
        if ov > 0.4 * (c["x1"] - c["x0"]) or ov > 0.6 * bw:
            out.append(c["id"])
    return out


# ---------------------------------------------------------------- hyphenation
HYPHEN = re.compile(r"[-¬⸗=]$")
TERMINAL = re.compile(r"[.!?][\"»“”')]?$")


def first_alpha(t):
    return next((ch for ch in t if ch.isalpha()), "")


def hyphen_link(a, b):
    """Line/paragraph a ends with a word-division hyphen and b continues in lowercase."""
    return bool(HYPHEN.search(a.rstrip())) and first_alpha(b).islower()


def order_score(seq):
    """Score a block order by word divisions and sentence continuity at block joints.

    +1   block ends with hyphen, next text block starts lowercase
    -1   block ends with hyphen, next block starts uppercase / is a title
    +0.5 no sentence end, next text block starts lowercase
    -0.5 sentence end, next text block starts lowercase
    """
    score, ok, bad = 0.0, 0, 0
    for a, b in zip(seq, seq[1:]):
        if a["type"] != "text":
            continue
        ta, tb = a["lines"][-1]["text"].rstrip(), b["lines"][0]["text"]
        low = b["type"] == "text" and first_alpha(tb).islower()
        if HYPHEN.search(ta):
            if low:
                score, ok = score + 1, ok + 1
            else:
                score, bad = score - 1, bad + 1
        elif low:
            score += -0.5 if TERMINAL.search(ta) else 0.5
    return score, ok, bad


# ---------------------------------------------------------------- paragraphs
def join_lines(texts):
    out = ""
    for t in texts:
        if not out:
            out = t
        elif re.search(r"[-¬⸗=]$", out) and t[:1].islower():
            out = out[:-1] + t
        else:
            out += " " + t
    return out


def split_paragraphs(block, pitch):
    lines = block["lines"]
    if block["type"] == "title" or len(lines) == 1:
        return [lines]
    left = sorted(l["bbox"][0] for l in lines)[len(lines) // 5]
    right = sorted(l["bbox"][2] for l in lines)[(4 * len(lines)) // 5]
    paras, cur = [], [lines[0]]
    for prev, ln in zip(lines, lines[1:]):
        indent = ln["bbox"][0] - left > 0.7 * pitch
        short_prev = prev["bbox"][2] < right - 1.5 * pitch
        gap = ln["baseline_y"] - prev["baseline_y"] > 1.7 * pitch
        if (indent or short_prev or gap) and not hyphen_link(prev["text"], ln["text"]):
            paras.append(cur)
            cur = []
        cur.append(ln)
    paras.append(cur)
    return paras


# ---------------------------------------------------------------- rules
def load_rules(path, W, H, gutters, pitch):
    """Horizontal rules that cross at least one column gutter (span >= 2 columns)."""
    if not path.exists():
        return []
    out = []
    for r in json.loads(path.read_text())["rules"]:
        x0, y0, x1, y1 = r["bbox"]
        if y1 < 0.015 * H or y0 > 0.985 * H:            # scan border
            continue
        if not any(x0 < g - 2 * pitch and x1 > g + 2 * pitch for g in gutters):
            continue
        out.append({"bbox": [x0, y0, x1, y1], "is_rule": True, "type": "rule"})
    return out


def chars(items):
    return sum(len(l["text"]) for it in items for l in it.get("lines", []))


def order_with_rules(items, sec_rules, loc_rules, pitch, gutters, streams=None, stream="main"):
    """Rules in 'section' mode: content below the rule (within its x-range) is read
    after the rest of the region (e.g. feuilleton under a full or half-width rule).
    Rules in 'local' mode only act as separators inside XY-cut.
    If `streams` is a dict, blocks get a text-stream label: content below a section
    rule that holds less than half of the region's text is a separate stream
    ("below_rule", e.g. feuilleton); a rule under the masthead keeps "main"."""
    if sec_rules:
        R = min(sec_rules, key=lambda r: r["bbox"][1])
        x0, _, x1, y1 = R["bbox"]

        def below(it):
            cx = (it["bbox"][0] + it["bbox"][2]) / 2
            return x0 - pitch <= cx <= x1 + pitch and it["bbox"][1] >= y1 - 0.5 * pitch

        others = [r for r in sec_rules if r is not R]
        bel = [it for it in items if below(it)]
        rest = [it for it in items if not below(it)]
        if not bel or not rest:
            return order_with_rules(items, others, loc_rules, pitch, gutters, streams, stream)
        bel_stream = "below_rule" if chars(bel) < 0.5 * chars(items) else stream
        return (order_with_rules(rest, [r for r in others if not below(r)],
                                 [r for r in loc_rules if not below(r)], pitch, gutters, streams, stream)
                + order_with_rules(bel, [r for r in others if below(r)],
                                   [r for r in loc_rules if below(r)], pitch, gutters, streams, bel_stream))
    out = [it for it in xycut(list(items) + list(loc_rules), pitch, gutters) if not it.get("is_rule")]
    if streams is not None:
        for it in out:
            streams[id(it)] = stream
    return out


def choose_order(blocks, rules, pitch, gutters):
    """Pick rule modes greedily so that the hyphenation score is maximal
    (ties keep the earlier, more structural choice: section > local > ignore)."""
    def run(modes):
        sec = [r for r, m in zip(rules, modes) if m == "section"]
        loc = [r for r, m in zip(rules, modes) if m == "local"]
        order = order_with_rules(blocks, sec, loc, pitch, gutters)
        return order, order_score(order)

    modes = ["section"] * len(rules)
    order, best = run(modes)
    for i in range(len(rules)):
        for m in ("local", "ignore"):
            trial = modes[:i] + [m] + modes[i + 1:]
            o, sc = run(trial)
            if sc[0] > best[0]:
                modes, order, best = trial, o, sc
    streams = {}
    order_with_rules(blocks, [r for r, m in zip(rules, modes) if m == "section"],
                     [r for r, m in zip(rules, modes) if m == "local"], pitch, gutters, streams)
    return order, modes, best, streams


# ---------------------------------------------------------------- page analysis
def text_extent(b, cols):
    """Left/right text margin of a block (for indentation / full-line tests)."""
    xs0 = sorted(l["bbox"][0] for l in b["lines"])
    xs1 = sorted(l["bbox"][2] for l in b["lines"])
    n = len(xs0)
    if n >= 3:
        return xs0[n // 5], xs1[(4 * n) // 5]
    cs = [c for c in cols if c["id"] in b.get("columns", [])]
    if len(cs) == 1:
        return cs[0]["x0"], cs[0]["x1"]
    return b["bbox"][0], b["bbox"][2]


def analyze(page_no, uuid, xml_path, yolo, rules_path):
    W, H, lines = read_page_xml(xml_path)

    # typical line pitch from pero line heights (bbox height ~ 1.2 x pitch)
    pitch = st.median(l["bbox"][3] - l["bbox"][1] for l in lines) * 0.85
    noise = [l for l in lines if is_noise(l, W, pitch)]
    lines = [l for l in lines if not is_noise(l, W, pitch)]

    blocks, runin = build_blocks(lines, yolo, pitch)
    cols = detect_columns(lines, W, H)
    gutters = column_gutters(cols)
    rules = load_rules(rules_path, W, H, gutters, pitch)
    order, modes, (score, h_ok, h_bad), streams = choose_order(blocks, rules, pitch, gutters)

    # running header: >= 2 blocks in the topmost short band
    top = min(b["bbox"][1] for b in order)
    head = [b for b in order if b["bbox"][3] <= top + 2.5 * pitch]
    head_ids = {id(b) for b in head} if len(head) >= 2 else set()

    out_blocks = []
    p_counter = 0
    for bi, b in enumerate(order, 1):
        b["columns"] = block_columns(b, cols)
        left, right = text_extent(b, cols)
        paras = []
        for pi, pl in enumerate(split_paragraphs(b, pitch), 1):
            p_counter += 1
            has_runin = any(inter_area(r, pl[0]["bbox"]) > 0.5 * area(r) for r in runin)
            paras.append({
                "id": f"p{page_no}-b{bi}-p{pi}", "order": p_counter,
                "bbox": union([l["bbox"] for l in pl]), "runin_title": has_runin,
                "text": join_lines([l["text"] for l in pl]),
                "lines": [{k: l[k] for k in ("id", "bbox", "polygon", "baseline", "text", "conf")} for l in pl],
            })
        out_blocks.append({
            "id": f"p{page_no}-b{bi}", "order": bi,
            "type": b["type"], "role": "header" if id(b) in head_ids else "body",
            "stream": streams.get(id(b), "main"),
            "source": b["source"], "yolo_conf": b.get("yolo_conf"), "bbox": b["bbox"],
            "columns": b["columns"], "text_left": left, "text_right": right,
            "paragraphs": paras,
        })

    return {
        "page_no": page_no, "uuid": uuid, "image": f"{uuid}.jpg", "width": W, "height": H,
        "line_pitch": round(pitch, 1), "columns": cols,
        "rules": [{"bbox": r["bbox"], "mode": m} for r, m in zip(rules, modes)],
        "reading_order": {"hyphen_score": score, "hyphen_links_ok": h_ok, "hyphen_links_broken": h_bad},
        "blocks": out_blocks,
        "noise_lines": [{k: l[k] for k in ("id", "bbox", "text", "conf")} for l in noise],
        "stats": {"columns": len(cols), "blocks": len(out_blocks), "paragraphs": p_counter,
                  "lines": len(lines), "chars": sum(len(l["text"]) for l in lines),
                  "noise_lines": len(noise), "rules": len(rules),
                  "hyphen_ok": h_ok, "hyphen_broken": h_bad},
    }


# ---------------------------------------------------------------- paragraph flow
def continues(a, ablk, apitch, b, bblk, bpitch):
    """Does paragraph b (first in its block) continue paragraph a (last in its block)?"""
    la, lb = a["lines"][-1], b["lines"][0]
    if HYPHEN.search(la["text"].rstrip()):
        return first_alpha(lb["text"]).islower()
    if first_alpha(lb["text"]).islower() and not TERMINAL.search(la["text"].rstrip()):
        return True
    full = la["bbox"][2] >= ablk["text_right"] - 1.5 * apitch
    no_indent = lb["bbox"][0] <= bblk["text_left"] + 0.7 * bpitch
    return full and no_indent


def link_flow(pages):
    """Join paragraphs that flow across blocks, columns and pages.

    Links are searched separately in each text stream ("main", "below_rule" =
    e.g. feuilleton), so a feuilleton continues in the feuilleton of the next
    page and the main text in the main text.  Adds 'flow' to every paragraph and
    returns the logical paragraphs in reading order."""
    prev_of = {}
    for stream in ("main", "below_rule"):
        seq = [(pg, b, p, i == 0, i == len(b["paragraphs"]) - 1)
               for pg in pages for b in pg["blocks"]
               if b["role"] != "header" and b["stream"] == stream
               for i, p in enumerate(b["paragraphs"])]
        for (ppg, pb, pp, _, plast), (pg, b, p, first, _) in zip(seq, seq[1:]):
            if (plast and first and pb["type"] == "text" and b["type"] == "text"
                    and continues(pp, pb, ppg["line_pitch"], p, b, pg["line_pitch"])):
                prev_of[p["id"]] = pp

    logical, of = [], {}
    for pg in pages:
        for b in pg["blocks"]:
            for p in b["paragraphs"]:
                if b["role"] == "header":
                    p["flow"] = {"id": None, "prev": None, "next": None}
                    continue
                part = {"page": pg["page_no"], "paragraph": p["id"], "block": b["order"]}
                pp = prev_of.get(p["id"])
                if pp is not None:
                    L = of[pp["id"]]
                    pp["flow"]["next"] = p["id"]
                    p["flow"] = {"id": L["id"], "prev": pp["id"], "next": None}
                    L["parts"].append(part)
                    L["texts"].append(p["text"])
                else:
                    L = {"id": f"L{len(logical) + 1}", "type": b["type"], "stream": b["stream"],
                         "parts": [part], "texts": [p["text"]]}
                    logical.append(L)
                    p["flow"] = {"id": L["id"], "prev": None, "next": None}
                of[p["id"]] = L
    for L in logical:
        L["text"] = join_lines(L.pop("texts"))
        L["pages"] = sorted({x["page"] for x in L["parts"]})
    return logical


def page_text(page):
    out = [f"=== Strana {page['page_no']} ({page['uuid']}) ==="]
    for b in page["blocks"]:
        for p in b["paragraphs"]:
            prefix = "## " if b["type"] == "title" else ""
            out.append(prefix + p["text"])
    return "\n\n".join(out) + "\n"


def issue_text(pages, logical):
    out, seen_page = [], 0
    first_page = {L["id"]: L["parts"][0]["page"] for L in logical}
    by_page = {}
    for L in logical:
        by_page.setdefault(first_page[L["id"]], []).append(L)
    for pg in pages:
        out.append(f"=== Strana {pg['page_no']} ===")
        for b in pg["blocks"]:
            if b["role"] == "header":
                out.append("[záhlaví] " + " ".join(p["text"] for p in b["paragraphs"]))
        for L in by_page.get(pg["page_no"], []):
            more = f"  [pokračuje na str. {', '.join(map(str, L['pages'][1:]))}]" if len(L["pages"]) > 1 else ""
            out.append(("## " if L["type"] == "title" else "") + L["text"] + more)
    return "\n\n".join(out) + "\n"


def read_order(path):
    """page order: PressMint idMapping JSONL ({n, uuid, url, ...} per line)
    or TSV  page_no<TAB>uuid[<TAB>label]  ->  [(page_no, uuid, url|None)]"""
    rows = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        if line.lstrip().startswith("{"):
            d = json.loads(line)
            rows.append((int(d["n"]), d["uuid"], d.get("url")))
        else:
            no, uuid = line.split("\t")[:2]
            rows.append((int(no), uuid, None))
    return sorted(rows)


def read_regions(path):
    """YOLO regions per page uuid: PressMint imageRegions JSONL (Scripts/yoloLayout.py,
    one region per line) or a directory with one <uuid>.json per page (yolo_regions.py)"""
    path = Path(path)
    if path.is_file():
        regions = {}
        for line in path.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                regions.setdefault(d["image"]["uuid"], []).append(
                    {"bbox": [round(v) for v in d["bbox_xyxy"]], "cls": d["class_name"],
                     "conf": round(d["confidence"], 3)})
        return lambda uuid: regions.get(uuid, [])
    return lambda uuid: (json.loads((path / f"{uuid}.json").read_text())["regions"]
                         if (path / f"{uuid}.json").exists() else [])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--order", required=True, type=Path,
                    help="page order: idMapping JSONL, or TSV page_no<TAB>uuid")
    ap.add_argument("--xml", required=True, type=Path, help="dir with PAGE XML <uuid>.xml")
    ap.add_argument("--yolo", required=True, type=Path,
                    help="YOLO regions: imageRegions JSONL, or dir with <uuid>.json")
    ap.add_argument("--rules", type=Path, default=Path("/nonexistent"),
                    help="dir with detect_rules.py output <uuid>.json")
    ap.add_argument("-o", "--output", required=True, type=Path)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    regions = read_regions(args.yolo)
    pages = []
    for no, uuid, url in read_order(args.order):
        page = analyze(no, uuid, args.xml / f"{uuid}.xml", regions(uuid), args.rules / f"{uuid}.json")
        if url:
            page["url"] = url
        pages.append(page)
    logical = link_flow(pages)
    for page in pages:
        (args.output / f"{page['uuid']}.json").write_text(json.dumps(page, ensure_ascii=False, indent=1))
        (args.output / f"{page['uuid']}.txt").write_text(page_text(page))
        print(f"page {page['page_no']}: {page['stats']} rules={[r['mode'] for r in page['rules']]}")
    (args.output / "flow.json").write_text(json.dumps(logical, ensure_ascii=False, indent=1))
    (args.output / "all_pages.txt").write_text(issue_text(pages, logical))
    multi = [L for L in logical if len(L["parts"]) > 1]
    print(f"logical paragraphs: {len(logical)}, joined across blocks: {len(multi)}, "
          f"across pages: {sum(len(L['pages']) > 1 for L in logical)}")


if __name__ == "__main__":
    main()
