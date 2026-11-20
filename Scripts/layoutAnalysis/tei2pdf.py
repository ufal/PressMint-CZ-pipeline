#!/usr/bin/env python3
"""Render a TEI text + TEI facsimile pair (analysis2tei.py output) into a PDF that keeps
the page layout.

Only the TEI files are used (no image, no analysis JSON): every text line (lb) is drawn at
the position of its facsimile zone, scaled to the zone width.  On top of that:
  * frames: article (coloured, light fill), paragraph / head (thin), running head (fw, gray),
    separators (horizontal rules from the facsimile)
  * reading order: numbered circles at the start of every column segment of an article and
    arrows between consecutive segments (main text solid, feuilleton dashed);
    paragraphs continuing on another page are marked "→ str. N" / "str. N →"
  * outline: page → article (first head)
"""
import argparse
import math
import re
from pathlib import Path

from lxml import etree
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONTDIR = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("DV", FONTDIR + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DVB", FONTDIR + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("DVS", FONTDIR + "DejaVuSerif.ttf"))
pdfmetrics.registerFont(TTFont("DVSB", FONTDIR + "DejaVuSerif-Bold.ttf"))

TEI_NS = "http://www.tei-c.org/ns/1.0"
XID = "{http://www.w3.org/XML/1998/namespace}id"
PAGE_W = 842
TOP = 36           # header strip (pt)
ART_LABEL = {"banner": "banner", "advertisement": "inzerát"}
AD_COLOR = "#2e8b57"
PALETTE = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2",
           "#17becf", "#bcbd22", "#7f7f7f"]


def local(el):
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def box(el):
    return [float(el.get(k, 0)) for k in ("ulx", "uly", "lrx", "lry")]


def union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


# ---------------------------------------------------------------- TEI reading
def read_facs(path):
    root = etree.parse(str(path)).getroot()
    zones, surfaces = {}, []
    for s in root.iter(f"{{{TEI_NS}}}surface"):
        surf = {"id": s.get(XID), "n": s.get("n"), "box": box(s), "separators": []}
        surfaces.append(surf)
        for z in s.iter(f"{{{TEI_NS}}}zone"):
            zones[z.get(XID)] = {"surface": surf["id"], "type": z.get("type"),
                                 "subtype": z.get("subtype"), "box": box(z)}
            if z.get("type") == "separator":
                surf["separators"].append(zones[z.get(XID)])
    return surfaces, zones


def read_text(path, zones):
    """walk the TEI text in document order -> list of lines with their context"""
    root = etree.parse(str(path)).getroot()
    lines = []
    ctx = {"stream": None, "article": None, "block": None, "kind": None, "segment": None,
           "page": None, "fwseg": None}
    articles = {}
    cur = [None]

    def add_text(t):
        if t and cur[0] is not None:
            cur[0]["text"] += t

    def walk(el):
        tag = local(el)
        saved = dict(ctx)
        if tag == "div":
            if el.get("type") in ("article", "feuilleton", "banner", "advertisement"):
                # flat structure: body/div[@type=article|feuilleton]
                ctx["article"] = el.get(XID)
                ctx["stream"] = {"feuilleton": "feuilleton", "banner": "banner",
                                 "advertisement": "ads"}.get(el.get("type"), "main")
                articles[el.get(XID)] = {"id": el.get(XID), "stream": ctx["stream"],
                                         "n": len(articles) + 1, "heads": [], "type": el.get("type")}
            else:
                ctx["stream"] = el.get("type")
        elif tag in ("p", "head", "fw"):
            ctx["block"], ctx["kind"] = el.get(XID), tag
            if tag == "fw":
                ctx["fwseg"] = el.get("facs", "#")[1:]
            # the first line's lb (with pb/cb) stands right before the element:
            # that pending line belongs to this element
            if cur[0] is not None and cur[0]["block"] is None and not cur[0]["text"].strip():
                cur[0].update(block=ctx["block"], kind=tag, stream=ctx["stream"],
                              article=ctx["article"],
                              segment=ctx["fwseg"] if tag == "fw" else ctx["segment"])
            else:
                cur[0] = None                   # text before the first lb is not a line
        elif tag == "pb":
            ctx["page"] = zones[el.get("facs")[1:]]["surface"]
        elif tag == "cb":
            ctx["segment"] = el.get("facs")[1:]
        elif tag == "lb":
            z = zones.get(el.get("facs", "#")[1:])
            cur[0] = {"text": "", "box": z["box"] if z else None,
                      "surface": z["surface"] if z else ctx["page"],
                      "stream": ctx["stream"], "article": ctx["article"],
                      "block": ctx["block"], "kind": ctx["kind"],
                      "segment": ctx["segment"] if ctx["kind"] != "fw" else ctx["fwseg"]}
            lines.append(cur[0])
        elif tag == "pc":
            add_text(el.text)
        if tag not in ("pc",):
            add_text(el.text if tag not in ("lb", "pb", "cb") else None)
        for ch in el:
            walk(ch)
            add_text(ch.tail)
        if tag in ("p", "head", "fw"):
            cur[0] = None
        if tag in ("p", "head", "fw", "div"):
            # leaving the element restores context (but page/segment milestones persist)
            for k in ("stream", "article", "block", "kind"):
                ctx[k] = saved[k]

    walk(root)
    for l in lines:
        l["text"] = re.sub(r"\s+", " ", l["text"]).strip()
        a = articles.get(l["article"])
        if a is not None and l["kind"] == "head" and l["block"] not in [h[0] for h in a["heads"]]:
            a["heads"].append((l["block"], l["text"]))
        elif a is not None and l["kind"] == "head":
            # multi-line head: append text
            a["heads"] = [(b, t + " " + l["text"]) if b == l["block"] else (b, t) for b, t in a["heads"]]
    return lines, articles


# ---------------------------------------------------------------- drawing
def draw_arrow(c, x0, y0, x1, y1, size=5):
    c.line(x0, y0, x1, y1)
    ang = math.atan2(y1 - y0, x1 - x0)
    p = c.beginPath()
    p.moveTo(x1, y1)
    p.lineTo(x1 - size * math.cos(ang - 0.4), y1 - size * math.sin(ang - 0.4))
    p.lineTo(x1 - size * math.cos(ang + 0.4), y1 - size * math.sin(ang + 0.4))
    p.close()
    c.drawPath(p, stroke=0, fill=1)


def fit_text(c, text, x0, y0, x1, y1, font):
    """draw text into the box (PDF coords, y0 bottom) scaled to its width"""
    h = y1 - y0
    size = max(3.0, min(h * 0.78, 30))
    w = pdfmetrics.stringWidth(text, font, size)
    if w <= 0:
        return
    t = c.beginText()
    t.setFont(font, size)
    t.setHorizScale(max(40, min(160, 100 * (x1 - x0) / w)))
    t.setTextOrigin(x0, y0 + h * 0.22)
    t.textOut(text)
    c.drawText(t)


def render(text_path, facs_path, out, title):
    surfaces, zones = read_facs(facs_path)
    lines, articles = read_text(text_path, zones)
    # advertisements in one fixed colour, articles (and banner) by palette
    color_of = {a: colors.HexColor(AD_COLOR if art["type"] == "advertisement"
                                   else PALETTE[(art["n"] - 1) % len(PALETTE)])
                for a, art in articles.items()}

    # reading-order units = (stream, article, segment) in document order
    units, seen = [], {}
    for l in lines:
        if l["box"] is None or l["kind"] == "fw":
            continue
        key = (l["surface"], l["stream"], l["article"], l["segment"])
        if key not in seen:
            seen[key] = {"key": key, "surface": l["surface"], "stream": l["stream"],
                         "article": l["article"], "boxes": [], "blocks": []}
            units.append(seen[key])
        seen[key]["boxes"].append(l["box"])
        if l["block"] not in seen[key]["blocks"]:
            seen[key]["blocks"].append(l["block"])
    # blocks (p/head) appearing on several surfaces -> cross-page continuation
    block_surfaces = {}
    for l in lines:
        if l["box"] is not None:
            block_surfaces.setdefault(l["block"], [])
            if l["surface"] not in block_surfaces[l["block"]]:
                block_surfaces[l["block"]].append(l["surface"])
    surf_n = {s["id"]: s["n"] for s in surfaces}

    c = canvas.Canvas(str(out))
    c.setTitle(title)
    for si, s in enumerate(surfaces):
        W, H = s["box"][2], s["box"][3]
        k = PAGE_W / W
        ph = H * k + TOP
        c.setPageSize((PAGE_W, ph))

        def X(x):
            return x * k

        def Y(y):
            return ph - TOP - y * k

        def rect(b):
            return X(b[0]), Y(b[3]), X(b[2]) - X(b[0]), Y(b[1]) - Y(b[3])

        c.bookmarkPage(s["id"])
        c.addOutlineEntry(f"Strana {s['n']}", s["id"], level=0)
        c.setFont("DVB", 11)
        c.setFillColor(colors.black)
        c.drawString(10, ph - 17, f"{title} – strana {s['n']}")
        c.setFont("DV", 7)
        c.drawString(10, ph - 29,
                          "rámečky: článek (barva), inzerát (zeleně), odstavec/nadpis · "
                          "kroužky a šipky: pořadí čtení (fejeton čárkovaně)")

        page_units = [u for u in units if u["surface"] == s["id"]]
        page_lines = [l for l in lines if l["surface"] == s["id"] and l["box"] is not None]

        # article frames (one rectangle per column segment), light fill
        for u in page_units:
            col = color_of.get(u["article"], colors.gray)
            b = union(u["boxes"])
            pad = 6
            b = [b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad]
            c.setStrokeColor(col)
            c.setFillColor(col, alpha=0.07)
            c.setLineWidth(1.4)
            c.setDash([4, 2] if u["stream"] == "feuilleton" else [])
            c.rect(*rect(b), stroke=1, fill=1)
        c.setDash([])

        # paragraph / head / fw frames
        blocks = {}
        for l in page_lines:
            blocks.setdefault((l["block"], l["segment"]), []).append(l)
        for (bid, _), ls in blocks.items():
            b = union([l["box"] for l in ls])
            kind = ls[0]["kind"]
            col = colors.gray if kind == "fw" else color_of.get(ls[0]["article"], colors.gray)
            c.setStrokeColor(col, alpha=0.9 if kind == "head" else 0.5)
            c.setLineWidth(1.0 if kind == "head" else 0.4)
            c.rect(*rect([b[0] - 2, b[1] - 2, b[2] + 2, b[3] + 2]), stroke=1, fill=0)

        # separators
        c.setStrokeColor(colors.HexColor("#555555"))
        c.setLineWidth(1.2)
        for z in s["separators"]:
            b = z["box"]
            ym = (b[1] + b[3]) / 2
            c.setDash([] if z["subtype"] == "section" else [2, 2])
            c.line(X(b[0]), Y(ym), X(b[2]), Y(ym))
        c.setDash([])

        # text
        c.setFillColor(colors.black)
        for l in page_lines:
            if not l["text"]:
                continue
            b = l["box"]
            font = "DVSB" if l["kind"] == "head" else "DVS"
            if l["kind"] == "fw":
                c.setFillColor(colors.HexColor("#555555"))
            fit_text(c, l["text"], X(b[0]), Y(b[3]), X(b[2]), Y(b[1]), font)
            c.setFillColor(colors.black)

        # reading order: arrows between consecutive units of a stream, numbered circles
        for stream in ("banner", "main", "feuilleton", "ads"):
            seq = [u for u in page_units if u["stream"] == stream]
            c.setDash([4, 3] if stream == "feuilleton" else [])
            for a, b in zip(seq, seq[1:]):
                ba, bb = union(a["boxes"]), union(b["boxes"])
                col = color_of.get(b["article"], colors.gray)
                c.setStrokeColor(col, alpha=0.85)
                c.setFillColor(col, alpha=0.85)
                c.setLineWidth(1.6)
                x0, y0 = X((ba[0] + ba[2]) / 2), Y(ba[3])
                x1, y1 = X(bb[0]) + 9, Y(bb[1]) + 9
                draw_arrow(c, x0, y0, x1, y1, size=7)
            c.setDash([])
        for i, u in enumerate(page_units, 1):
            b = union(u["boxes"])
            col = color_of.get(u["article"], colors.gray)
            cx, cy = X(b[0]) + 9, Y(b[1]) + 9
            c.setFillColor(col)
            c.setStrokeColor(colors.white)
            c.circle(cx, cy, 7.5, stroke=1, fill=1)
            c.setFillColor(colors.white)
            c.setFont("DVB", 7)
            c.drawCentredString(cx, cy - 2.5, str(i))
            art = articles.get(u["article"])
            # article label at its first unit in the whole issue
            if art and units.index(u) == next(j for j, v in enumerate(units) if v["article"] == u["article"]):
                c.setFillColor(col)
                c.setFont("DVB", 7)
                c.drawString(cx + 10, cy - 2.5, ART_LABEL.get(art["type"], f"čl. {art['n']}"))
                head = art["heads"][0][1] if art["heads"] else f"(článek {art['n']} bez nadpisu)"
                c.bookmarkHorizontal(f"{u['article']}", 0, cy + 10)
                c.addOutlineEntry(ART_LABEL.get(art["type"], f"čl. {art['n']}") + f": {head[:70]}", f"{u['article']}", level=1)

        # cross-page continuation labels
        c.setFont("DVB", 8)
        for bid, surfs in block_surfaces.items():
            if len(surfs) < 2 or s["id"] not in surfs:
                continue
            ls = [l for l in page_lines if l["block"] == bid]
            col = color_of.get(ls[0]["article"], colors.gray)
            c.setFillColor(col)
            i = surfs.index(s["id"])
            if i + 1 < len(surfs):
                b = ls[-1]["box"]
                c.drawRightString(X(b[2]), Y(b[3]) - 10, f"→ str. {surf_n[surfs[i + 1]]}")
            if i > 0:
                b = ls[0]["box"]
                c.drawString(X(b[0]) + 22, Y(b[1]) + 4, f"str. {surf_n[surfs[i - 1]]} →")
        c.showPage()
    c.save()
    print(f"written {out}: {len(surfaces)} pages, {len(articles)} articles, {len(lines)} lines")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--text", required=True, type=Path, help="TEI text file")
    ap.add_argument("--facs", required=True, type=Path, help="TEI facsimile file")
    ap.add_argument("--title", default=None)
    ap.add_argument("--meta", type=Path, help="meta.json (title, date) for the page header")
    ap.add_argument("-o", "--output", required=True, type=Path)
    args = ap.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    title = args.title or etree.parse(str(args.text)).getroot().get(XID)
    if args.meta and not args.title:
        import json
        m = json.loads(args.meta.read_text())
        title = f"{m['title']} {m['date']} ({title})"
    render(args.text, args.facs, args.output, title)


if __name__ == "__main__":
    main()
