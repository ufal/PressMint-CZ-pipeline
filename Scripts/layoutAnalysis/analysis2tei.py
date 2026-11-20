#!/usr/bin/env python3
"""Convert analyze_layout.py results of one issue into two TEI files.

Same conventions as Scripts/textRegions2teiFacsText (Sample/work/tei-text, tei-facs):
TEI/@xml:id = PressMint-CZ_<date>-<issue uuid prefix>, milestones pb/cb/lb in the text
point by @facs to zones of the facsimile and every zone points back by @start.

tei-text   TEI/text/front/div[@type=banner] (only if a banner was detected), then
           TEI/text/body/div  (flat: one div per article, direct children of body)
             div[@type=article] - main text: title(s) (head) + paragraphs up to the next title
             div[@type=banner] - masthead of the first page (title, date, prices, editor), in front
             div[@type=feuilleton] - the same for text below a section rule (after main text)
             pb  - page (one per page and text stream; feuilleton has its own pb)
             cb  - change of column (in reading order)
             head - title;  p - paragraph. A paragraph flowing to the next column/page
                   stays ONE p with cb/pb inside it. p/head start with text: the
                   pb/cb/lb opening them stand right before the element.
             lb  - line; lb[@break=no] after a divided word, the soft hyphen is
                   pc[@force=weak], a hard hyphen (next line starts uppercase) stays text
             running heads (page header) are left out; div ids = {id}.div{position}
tei-facs   TEI/facsimile/surface (page, graphic = url from idMapping or IIIF url)
             zone[@type=pageBody] - area of one text stream on the page (subtype belowRule
                                    for text under a section rule = feuilleton)
               zone[@type=column] - lines of a cb segment
                 zone[@type=line] - polygon of the text line
All xml:ids are checked to be unique across text and facsimile.
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
from lxml import etree
from scipy.spatial import ConvexHull, QhullError

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
XID = f"{{{XML_NS}}}id"
IIIF = "https://api.kramerius.mzk.cz/search/iiif/uuid:{uuid}/full/max/0/default.jpg"

HYPHEN = re.compile(r"[-¬⸗=]$")
# pero charset artifacts (same as textRegions2teiFacsText.clean_ocr_text)
OCR_ARTIFACTS = re.compile("[\ufffd\U00101010-\U0010102F]")
# div/@type of the articles of a text stream
STREAM_DIV = {"banner": "banner", "main": "article", "below_rule": "feuilleton"}
AREA_SUBTYPE = {"banner": "banner", "below_rule": "belowRule"}   # zone[@type=pageBody]/@subtype


def T(tag):
    return f"{{{TEI_NS}}}{tag}"


def clean(text):
    return re.sub(" {2,}", " ", OCR_ARTIFACTS.sub("", text)).strip()


def first_alpha(s):
    return next((ch for ch in s if ch.isalpha()), "")


def box_attrib(b):
    return {"ulx": str(int(b[0])), "uly": str(int(b[1])), "lrx": str(int(b[2])), "lry": str(int(b[3]))}


def union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def hull(points):
    pts = np.asarray(points, dtype=float)
    if len(pts) < 3:
        return []
    try:
        return [tuple(int(v) for v in pts[i]) for i in ConvexHull(pts).vertices]
    except QhullError:
        return []


def points_attrib(points):
    return {"points": " ".join(f"{x},{y}" for x, y in points)} if points else {}


class Zone:
    """facsimile zone collecting line geometry; bbox/hull are computed on close()."""

    def __init__(self, parent, zid, ztype, start, subtype=None):
        attrib = {XID: zid, "start": f"#{start}", "type": ztype}
        if subtype:
            attrib["subtype"] = subtype
        self.el = etree.SubElement(parent, T("zone"), attrib)
        self.id, self.points, self.boxes, self.n = zid, [], [], 0

    def add(self, pts, box):
        self.points += pts
        self.boxes.append(box)

    def close(self):
        if self.boxes:
            self.el.attrib.update(points_attrib(hull(self.points)))
            self.el.attrib.update(box_attrib(union(self.boxes)))
        return self


class Builder:
    def __init__(self, tei_id):
        self.id = tei_id
        self.text = etree.Element(T("TEI"), nsmap={None: TEI_NS},
                                  attrib={f"{{{XML_NS}}}lang": "cs", XID: tei_id})
        self.facs = etree.Element(T("TEI"), nsmap={None: TEI_NS},
                                  attrib={f"{{{XML_NS}}}lang": "cs", XID: tei_id})
        self.facsimile = etree.SubElement(self.facs, T("facsimile"))
        self.body = etree.SubElement(etree.SubElement(self.text, T("text")), T("body"))
        self.surfaces = {}
        self.n_pb = self.n_p = self.n_head = self.n_div = 0

    # ---- facsimile -------------------------------------------------------
    def surface(self, page):
        n = page["page_no"]
        if n not in self.surfaces:
            sid = f"{self.id}.f.pg{n}"
            s = etree.SubElement(self.facsimile, T("surface"), {
                XID: sid, "n": str(n), "ulx": "0", "uly": "0",
                "lrx": str(page["width"]), "lry": str(page["height"])})
            etree.SubElement(s, T("graphic"), {"url": page.get("url") or IIIF.format(uuid=page["uuid"])})
            self.surfaces[n] = {"el": s, "id": sid, "areas": 0, "page": page}
        return self.surfaces[n]

    # ---- one text stream -------------------------------------------------
    def stream(self, name, pages):
        """pages: [(page, body_blocks)] in issue order, blocks in reading order.
        Articles are direct children of body (PressMint sampling copies whole body children);
        the stream gives the article type: article (main text) / feuilleton (below a rule).
        The banner (masthead of the first page) goes to text/front, before body."""
        if name == "banner":
            front = etree.Element(T("front"))
            self.body.addprevious(front)
            self.div = front
        else:
            self.div = self.body
        self.div_type = STREAM_DIV.get(name, name)
        self.article = None           # open div (article)
        self.article_has_body = False # article already has a p (next title starts a new one)
        self.container = self.div     # where milestones go: div, or the open p
        self.p = None                 # open paragraph element
        self.tail = None              # element/str whose tail receives the next text
        self.pending_break = False    # previous line ended with a divided word
        for page, blocks in pages:
            self.close_zone()
            s = self.surface(page)
            s["areas"] += 1
            self.n_pb += 1
            pb_id = f"{self.id}.pb{self.n_pb}"
            self.area = Zone(s["el"], f"{s['id']}.a{s['areas']}", "pageBody", pb_id,
                             subtype=AREA_SUBTYPE.get(name))
            self.milestone("pb", pb_id, n=str(page["page_no"]), facs=f"#{self.area.id}")
            self.pb_id, self.n_cb, self.n_seg, self.col_key = pb_id, 0, 0, None
            for b in blocks:
                key = tuple(b.get("columns") or [b["id"]])
                if key != self.col_key:
                    self.column(key)
                for para in b["paragraphs"]:
                    self.paragraph(b, para)
            self.close_zone()
            self.area.close()
        self.close_p()

    def milestone(self, tag, mid, **attrib):
        a = {XID: mid}
        if self.pending_break:
            a["break"] = "no"
        a.update(attrib)
        el = etree.SubElement(self.container, T(tag), a)
        el.tail = "\n" if self.p is None else None
        if self.p is not None:
            self.tail = el
        return el

    def close_zone(self):
        z = getattr(self, "zone", None)
        if z is not None:
            z.close()
            self.area.add(z.points, union(z.boxes)) if z.boxes else None
        self.zone = None

    def column(self, key):
        self.close_zone()
        self.n_cb += 1
        self.n_seg += 1
        cb_id = f"{self.pb_id}.cb{self.n_cb}"
        self.zone = Zone(self.area.el, f"{self.area.id}.c{self.n_seg}", "column", cb_id)
        self.milestone("cb", cb_id, facs=f"#{self.zone.id}")
        self.col_key, self.cb_id, self.n_lb = key, cb_id, 0

    def line_zone(self, zone, line, i, lb_id):
        zid = f"{zone.id}.l{i}"
        poly = [tuple(p) for p in (line.get("polygon") or [])]
        etree.SubElement(zone.el, T("zone"), {XID: zid, "start": f"#{lb_id}", "type": "line",
                                              **points_attrib(poly), **box_attrib(line["bbox"])})
        zone.add(poly or [(line["bbox"][0], line["bbox"][1]), (line["bbox"][2], line["bbox"][3])],
                 line["bbox"])
        return zid

    def close_p(self):
        if self.p is not None:
            if self.tail is not None and self.tail is not self.p and self.tail.tail:
                self.tail.tail = self.tail.tail.rstrip()
            self.p.tail = "\n"
        self.p, self.tail, self.container = None, None, self.container_div()
        self.pending_break = False

    def container_div(self):
        return self.article if self.article is not None else self.div

    def new_article(self):
        """open a new article div; milestones (pb/cb) emitted since the last p/head
        belong to the new article, so they are moved into it"""
        prev = self.container_div()
        moved = []
        for el in reversed(list(prev)):
            if etree.QName(el).localname in ("pb", "cb"):
                moved.insert(0, el)
            else:
                break
        self.n_div += 1   # final ids are assigned by number_divs()
        self.article = etree.SubElement(self.div, T("div"), {XID: f"{self.id}.div{self.n_div}",
                                                            "type": self.div_type})
        self.article.text = "\n"
        self.article.tail = "\n"
        for el in moved:
            self.article.append(el)
        self.article_has_body = False
        self.container = self.article

    def append_text(self, text):
        if self.tail is self.p:
            self.p.text = (self.p.text or "") + text
        else:
            self.tail.tail = (self.tail.tail or "") + text

    def paragraph(self, block, para):
        flow = para.get("flow") or {}
        if not flow.get("prev") or self.p is None:
            self.close_p()
            title = block["type"] == "title"
            # article = title(s) + following paragraphs up to the next title;
            # the banner is one div: titles after its first text block are plain p
            if self.article is None or (title and self.article_has_body and self.div_type != "banner"):
                self.new_article()
            if title and self.article_has_body:
                title = False
            if title:
                self.n_head += 1
                tag, pid = "head", f"{self.id}.head{self.n_head}"
            else:
                self.article_has_body = True
                self.n_p += 1
                tag, pid = "p", f"{self.id}.p{self.n_p}"
            self.p = etree.SubElement(self.container, T(tag), {XID: pid})
            self.container, self.tail = self.p, self.p
        lines = [l for l in para["lines"] if clean(l["text"])]
        for i, line in enumerate(lines):
            text = clean(line["text"])
            self.n_lb += 1
            lb_id = f"{self.cb_id}.lb{self.n_lb}"
            z = self.line_zone(self.zone, line, self.n_lb, lb_id)
            if self.tail is not self.p or (self.p.text or ""):
                if not self.pending_break:
                    self.append_text("\n")
            self.milestone("lb", lb_id, facs=f"#{z}")
            self.pending_break = False
            # next line of the same logical paragraph (possibly in the next column / page)
            nxt = lines[i + 1]["text"] if i + 1 < len(lines) else (
                para.get("_next_first_line") if flow.get("next") else None)
            if HYPHEN.search(text) and nxt and len(text) > 1:
                self.pending_break = True
                if first_alpha(clean(nxt)).islower():
                    self.append_text(text[:-1])
                    pc = etree.SubElement(self.p, T("pc"), {"force": "weak"})
                    pc.text = text[-1]
                    self.tail = pc
                    continue
            self.append_text(text)
        if not flow.get("next"):
            self.close_p()


MILESTONES = ("pb", "cb", "lb")


def hoist_milestones(root):
    """p/head/fw start with text: milestones (pb, cb, lb) at the very beginning of such an
    element are moved right before it (inner ones – a paragraph flowing over a column or
    page break, following lines – stay inside)"""
    for el in list(root.iter(T("p"), T("head"))):
        parent = el.getparent()
        while len(el) and not (el.text or "").strip() and etree.QName(el[0]).localname in MILESTONES:
            m = el[0]
            el.text = m.tail
            m.tail = None
            el.remove(m)
            parent.insert(parent.index(el), m)


def number_divs(root, tei_id):
    """div ids by position in the document ({id}.div{n}, the same scheme as
    Scripts/addMissingIds.py), so no div is left without an id"""
    for i, d in enumerate(root.iter(T("div")), 1):
        attrs = [(k, v) for k, v in d.attrib.items() if k != XID]
        d.attrib.clear()
        d.set(XID, f"{tei_id}.div{i}")
        for k, v in attrs:
            d.set(k, v)


def check_unique_ids(tei_id, *roots):
    """text and facsimile end up in one document: every xml:id (except the shared
    TEI/@xml:id) must be unique across both"""
    seen, dup = set(), set()
    for root in roots:
        for el in root.iter():
            i = el.get(XID) if isinstance(el.tag, str) else None
            if i and el is not root:
                (dup if i in seen else seen).add(i)
    if dup:
        raise SystemExit(f"ERROR {tei_id}: duplicate xml:id: {', '.join(sorted(dup)[:10])}")


def load_pages(results):
    """page JSONs written by analyze_layout.py, in page order"""
    pages = [json.loads(f.read_text()) for f in Path(results).glob("*.json") if f.name != "flow.json"]
    return sorted(pages, key=lambda p: p["page_no"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--order", type=Path, help="(ignored, page order is taken from the results)")
    ap.add_argument("--meta", type=Path, help="meta.json with tei_id (CLAUDE-pipeline)")
    ap.add_argument("--tei-id", help="TEI/@xml:id (PressMint component id); default from --meta")
    ap.add_argument("--results", required=True, type=Path, help="analyze_layout.py output dir")
    ap.add_argument("--text", required=True, type=Path, help="output TEI text file")
    ap.add_argument("--facs", required=True, type=Path, help="output TEI facsimile file")
    args = ap.parse_args()

    tei_id = args.tei_id or json.loads(args.meta.read_text())["tei_id"]
    pages = load_pages(args.results)

    # first line of every paragraph, to decide soft/hard hyphen across blocks/pages
    first_line = {}
    for page in pages:
        for b in page["blocks"]:
            for para in b["paragraphs"]:
                ls = [l["text"] for l in para["lines"] if clean(l["text"])]
                if ls and para.get("flow", {}).get("id"):
                    first_line[para["id"]] = ls[0]
    flow_next = {}
    for page in pages:
        for b in page["blocks"]:
            for para in b["paragraphs"]:
                nxt = (para.get("flow") or {}).get("next")
                if nxt:
                    para["_next_first_line"] = first_line.get(nxt)
                    flow_next[para["id"]] = nxt

    tei = Builder(tei_id)
    # banner (masthead of the first page) first, then main text, then feuilleton
    for stream in ("banner", "main", "below_rule"):
        seq = []
        for page in pages:
            if stream == "banner":
                body = [b for b in page["blocks"] if b.get("role") == "banner"]
            else:
                # running heads (page header) are not part of the text
                body = [b for b in page["blocks"]
                        if b.get("role", "body") == "body" and b.get("stream", "main") == stream]
            body.sort(key=lambda b: b["order"])
            if stream == "main" or body:
                seq.append((page, body))
        if any(body for _, body in seq):
            tei.stream(stream, seq)
    hoist_milestones(tei.text)
    number_divs(tei.text, tei_id)
    check_unique_ids(tei_id, tei.text, tei.facs)

    for root, out in ((tei.text, args.text), (tei.facs, args.facs)):
        out.parent.mkdir(parents=True, exist_ok=True)
        etree.ElementTree(root).write(str(out), encoding="utf-8", xml_declaration=True, pretty_print=True)
    n_p = len(tei.text.findall(f".//{T('p')}"))
    n_lb = len(tei.text.findall(f".//{T('lb')}"))
    print(f"{tei_id}: {len(pages)} pages, {n_p} p, {n_lb} lb -> {args.text}, {args.facs}")


if __name__ == "__main__":
    main()
