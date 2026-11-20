#!/usr/bin/env python3
"""Render analysis results (analyze_layout.py JSON) into one PDF.

For every newspaper page:
  1. layout   – columns, blocks (title/text), reading order (numbers + arrows),
                invisible OCR text layer (searchable / selectable)
  2. paragraphs – paragraph boxes and line baselines
  3. text     – recognized text in reading order with block/column/paragraph labels
"""
import argparse
import io
import json
from pathlib import Path

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Frame, Paragraph, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

FONTDIR = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("DV", FONTDIR + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DVB", FONTDIR + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("DVS", FONTDIR + "DejaVuSerif.ttf"))
pdfmetrics.registerFont(TTFont("DVSB", FONTDIR + "DejaVuSerif-Bold.ttf"))
from reportlab.pdfbase.pdfmetrics import registerFontFamily
registerFontFamily("DVS", normal="DVS", bold="DVSB", italic="DVS", boldItalic="DVSB")
registerFontFamily("DV", normal="DV", bold="DVB", italic="DV", boldItalic="DVB")

COL_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#17becf"]
TYPE_COLOR = {"title": colors.HexColor("#d62728"), "text": colors.HexColor("#1f4e9c")}
PARA_COLORS = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00", "#a65628"]
PAGE_W = 842.0  # points; height follows image aspect ratio
IMG_MAX_W = 2000  # downscale embedded raster


def alpha(hexcol, a):
    c = colors.HexColor(hexcol)
    return colors.Color(c.red, c.green, c.blue, alpha=a)


def load_image(path):
    im = Image.open(path).convert("L")
    if im.width > IMG_MAX_W:
        im = im.resize((IMG_MAX_W, round(im.height * IMG_MAX_W / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=70)
    buf.seek(0)
    return ImageReader(buf)


class PageMapper:
    def __init__(self, page):
        self.s = PAGE_W / page["width"]
        self.W, self.H = PAGE_W, page["height"] * self.s

    def x(self, v):
        return v * self.s

    def y(self, v):
        return self.H - v * self.s

    def rect(self, b):  # x, y, w, h in PDF coords
        return self.x(b[0]), self.y(b[3]), (b[2] - b[0]) * self.s, (b[3] - b[1]) * self.s


def header(c, m, text):
    c.setFillColor(colors.Color(1, 1, 1, alpha=0.85))
    c.rect(0, m.H - 18, m.W, 18, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setFont("DVB", 10)
    c.drawString(8, m.H - 13, text)


def text_layer(c, m, page):
    """Invisible text at line positions -> PDF is searchable / copyable."""
    for b in page["blocks"]:
        for p in b["paragraphs"]:
            for ln in p["lines"]:
                if not ln["text"]:
                    continue
                x0, y0, x1, y1 = ln["bbox"]
                size = max(2.0, (y1 - y0) * m.s * 0.7)
                t = c.beginText()
                t.setTextRenderMode(3)
                t.setFont("DV", size)
                w = pdfmetrics.stringWidth(ln["text"], "DV", size) or 1
                t.setHorizScale(100.0 * (x1 - x0) * m.s / w)
                base = ln["baseline"][0][1] if ln["baseline"] else y1
                t.setTextOrigin(m.x(x0), m.y(base))
                t.textOut(ln["text"])
                c.drawText(t)


def draw_arrow(c, x0, y0, x1, y1, size=5):
    import math
    c.line(x0, y0, x1, y1)
    ang = math.atan2(y1 - y0, x1 - x0)
    p = c.beginPath()
    p.moveTo(x1, y1)
    p.lineTo(x1 - size * math.cos(ang - 0.4), y1 - size * math.sin(ang - 0.4))
    p.lineTo(x1 - size * math.cos(ang + 0.4), y1 - size * math.sin(ang + 0.4))
    p.close()
    c.drawPath(p, stroke=0, fill=1)


def layout_page(c, page, img):
    m = PageMapper(page)
    c.setPageSize((m.W, m.H))
    c.drawImage(img, 0, 0, m.W, m.H)

    # columns
    for i, col in enumerate(page["columns"]):
        cc = COL_COLORS[i % len(COL_COLORS)]
        c.setFillColor(alpha(cc, 0.10))
        c.setStrokeColor(alpha(cc, 0.6))
        c.setLineWidth(0.8)
        c.setDash(4, 3)
        c.rect(*m.rect([col["x0"], col["y0"], col["x1"], col["y1"]]), stroke=1, fill=1)
        c.setDash()
        c.setFillColor(colors.HexColor(cc))
        c.setFont("DVB", 9)
        c.drawCentredString(m.x((col["x0"] + col["x1"]) / 2), m.y(col["y1"]) - 10,
                            f"sloupec {i + 1}")

    # horizontal rules (separators) and the mode chosen by the hyphenation score
    for r in page.get("rules", []):
        x0, y0, x1, y1 = r["bbox"]
        y = m.y((y0 + y1) / 2)
        if r["mode"] == "section":
            c.setStrokeColor(colors.Color(1, 0.45, 0, alpha=0.9)); c.setLineWidth(3); c.setDash()
            lab = "čára: pod ní samostatná sekce"
        elif r["mode"] == "local":
            c.setStrokeColor(colors.Color(1, 0.45, 0, alpha=0.9)); c.setLineWidth(2); c.setDash(6, 3)
            lab = "čára: lokální oddělovač"
        else:
            c.setStrokeColor(colors.Color(0.4, 0.4, 0.4, alpha=0.8)); c.setLineWidth(1.5); c.setDash(2, 2)
            lab = "čára: ignorována"
        c.line(m.x(x0), y, m.x(x1), y)
        c.setDash()
        c.setFont("DVB", 6.5)
        c.setFillColor(colors.Color(0.8, 0.3, 0) if r["mode"] != "ignore" else colors.grey)
        c.drawString(m.x(x0) + 2, y + 2.5, lab)

    # blocks
    for b in page["blocks"]:
        col = TYPE_COLOR[b["type"]] if b.get("role") != "header" else colors.HexColor("#777777")
        c.setStrokeColor(col)
        c.setLineWidth(1.4 if b["source"] == "yolo" else 1.0)
        if b["source"] != "yolo":
            c.setDash(2, 2)
        c.setFillColor(colors.Color(col.red, col.green, col.blue, alpha=0.07))
        c.rect(*m.rect(b["bbox"]), stroke=1, fill=1)
        c.setDash()

    # reading order arrows
    centers = [((b["bbox"][0] + b["bbox"][2]) / 2, (b["bbox"][1] + b["bbox"][3]) / 2) for b in page["blocks"]]
    c.setStrokeColor(colors.Color(0.85, 0, 0.6, alpha=0.75))
    c.setFillColor(colors.Color(0.85, 0, 0.6, alpha=0.75))
    c.setLineWidth(1.1)
    for (ax, ay), (bx, by) in zip(centers, centers[1:]):
        draw_arrow(c, m.x(ax), m.y(ay), m.x(bx), m.y(by))

    # order numbers
    for b in page["blocks"]:
        x, y = m.x(b["bbox"][0]), m.y(b["bbox"][1])
        lab = str(b["order"])
        c.setFont("DVB", 7)
        w = pdfmetrics.stringWidth(lab, "DVB", 7) + 4
        c.setFillColor(TYPE_COLOR[b["type"]] if b.get("role") != "header" else colors.HexColor("#777777"))
        c.roundRect(x, y - 9, w, 9, 2, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.drawString(x + 2, y - 7, lab)

    text_layer(c, m, page)
    ro = page.get("reading_order", {})
    header(c, m, f"Strana {page['page_no']} – sloupce, bloky, pořadí čtení (červeně nadpis, modře text, šedě záhlaví, "
                 f"čárkovaně mimo YOLO; oranžově čáry)   dělená slova na spojích: "
                 f"{ro.get('hyphen_links_ok', 0)} ✓ / {ro.get('hyphen_links_broken', 0)} ✗")
    c.bookmarkPage(f"layout{page['page_no']}")
    c.addOutlineEntry(f"Strana {page['page_no']}", f"layout{page['page_no']}", level=0)
    c.addOutlineEntry(f"Strana {page['page_no']} – layout a pořadí čtení", f"layout{page['page_no']}", level=1)
    c.showPage()


def para_page(c, page, img, pindex):
    m = PageMapper(page)
    c.setPageSize((m.W, m.H))
    c.drawImage(img, 0, 0, m.W, m.H)
    for b in page["blocks"]:
        for p in b["paragraphs"]:
            cc = PARA_COLORS[p["order"] % len(PARA_COLORS)]
            c.setStrokeColor(colors.HexColor(cc))
            c.setFillColor(alpha(cc, 0.12))
            c.setLineWidth(0.9)
            c.rect(*m.rect(p["bbox"]), stroke=1, fill=1)
            c.setStrokeColor(alpha(cc, 0.7))
            c.setLineWidth(0.4)
            for ln in p["lines"]:
                if ln["baseline"]:
                    path = c.beginPath()
                    path.moveTo(m.x(ln["baseline"][0][0]), m.y(ln["baseline"][0][1]))
                    for x, y in ln["baseline"][1:]:
                        path.lineTo(m.x(x), m.y(y))
                    c.drawPath(path, stroke=1, fill=0)
            c.setFont("DVB", 5.5)
            c.setFillColor(colors.HexColor(cc))
            c.drawRightString(m.x(p["bbox"][2]) - 1, m.y(p["bbox"][1]) - 6, f"¶{p['order']}")
    # paragraph flow across blocks / columns / pages
    c.setStrokeColor(colors.Color(0, 0.6, 0.2, alpha=0.9))
    c.setFillColor(colors.Color(0, 0.6, 0.2, alpha=0.9))
    c.setLineWidth(1.6)
    for b in page["blocks"]:
        for p in b["paragraphs"]:
            fl = p.get("flow") or {}
            last = p["lines"][-1]["bbox"]
            if fl.get("next"):
                npg, np_ = pindex[fl["next"]]
                if npg == page["page_no"]:
                    first = np_["lines"][0]["bbox"]
                    c.setDash(5, 3)
                    draw_arrow(c, m.x(last[2]), m.y(last[3]), m.x(first[0]), m.y(first[1]), size=7)
                    c.setDash()
                else:
                    c.setFont("DVB", 8)
                    c.drawString(m.x(last[2]) + 2, m.y(last[3]), f"→ str. {npg}")
            if fl.get("prev"):
                ppg, _ = pindex[fl["prev"]]
                if ppg != page["page_no"]:
                    first = p["lines"][0]["bbox"]
                    c.setFont("DVB", 8)
                    c.drawRightString(m.x(first[0]) - 2, m.y(first[1]) - 8, f"str. {ppg} →")
    for n in page["noise_lines"]:
        c.setStrokeColor(colors.Color(0.5, 0.5, 0.5, alpha=0.8))
        c.setLineWidth(0.5)
        c.rect(*m.rect(n["bbox"]), stroke=1, fill=0)
    text_layer(c, m, page)
    header(c, m, f"Strana {page['page_no']} – odstavce (¶ = pořadí) a řádky; zeleně přetékání odstavce do dalšího bloku / sloupce / strany")
    c.bookmarkPage(f"para{page['page_no']}")
    c.addOutlineEntry(f"Strana {page['page_no']} – odstavce a řádky", f"para{page['page_no']}", level=1)
    c.showPage()


STY = {
    "h1": ParagraphStyle("h1", fontName="DVB", fontSize=15, leading=19, spaceAfter=8),
    "label": ParagraphStyle("label", fontName="DV", fontSize=6.5, leading=8, textColor=colors.grey),
    "title": ParagraphStyle("title", fontName="DVSB", fontSize=11, leading=14, spaceBefore=4, spaceAfter=2),
    "text": ParagraphStyle("text", fontName="DVS", fontSize=9, leading=11.5, spaceAfter=5, alignment=4),
    "body": ParagraphStyle("body", fontName="DV", fontSize=9.5, leading=13, spaceAfter=6),
}


def flow(c, story, title, key, level=1):
    first = True
    while story:
        c.setPageSize(A4)
        if first:
            c.bookmarkPage(key)
            c.addOutlineEntry(title, key, level=level)
            first = False
        f = Frame(40, 40, A4[0] - 80, A4[1] - 80, showBoundary=0)
        f.addFromList(story, c)
        c.setFont("DV", 7)
        c.setFillColor(colors.grey)
        c.drawRightString(A4[0] - 40, 25, title)
        c.showPage()


def text_pages(c, page, logical, pindex):
    story = [Paragraph(f"Strana {page['page_no']} – rozpoznaný text v pořadí čtení", STY["h1"])]
    for b in page["blocks"]:
        cols = ",".join(x.lstrip("c") for x in b["columns"]) or "–"
        kind = "záhlaví" if b.get("role") == "header" else ("nadpis" if b["type"] == "title" else "text")
        for p in b["paragraphs"]:
            fl = p.get("flow") or {}
            confs = [l["conf"] for l in p["lines"] if l["conf"] is not None]
            conf = f"{sum(confs) / len(confs):.2f}" if confs else "–"
            label = (f"blok {b['order']} ({kind}{', mimo YOLO' if b['source'] != 'yolo' else ''}) · "
                     f"sloupec {cols} · ¶{p['order']} · {len(p['lines'])} ř. · conf {conf}")
            if fl.get("prev"):
                ppg, pp = pindex[fl["prev"]]
                where = f"str. {ppg}, " if ppg != page["page_no"] else ""
                story.append(Paragraph(label + f" · <font color='#1a8f3a'>↳ pokračování odstavce z {where}"
                                       f"¶{pp['order']} – text je připojen tam</font>", STY["label"]))
                continue
            text = p["text"]
            if fl.get("next") and fl.get("id") in logical:
                L = logical[fl["id"]]
                text = L["text"]
                parts = []
                for x in L["parts"]:
                    xpg, xp = pindex[x["paragraph"]]
                    parts.append((f"str. {xpg} " if xpg != page["page_no"] else "") + f"¶{xp['order']}")
                label += f" · <font color='#1a8f3a'>sloučeno: {' + '.join(parts)}</font>"
            story.append(Paragraph(label, STY["label"]))
            story.append(Paragraph(escape(text) or "&nbsp;",
                                   STY["title"] if b["type"] == "title" else STY["text"]))
    flow(c, story, f"Strana {page['page_no']} – text", f"text{page['page_no']}")


def intro(c, pages, title, logical):
    story = [Paragraph(escape(title), STY["h1"]),
             Paragraph("Automatické rozpoznání textu a struktury stran. Postup:", STY["body"]),
             Paragraph("1. <b>Text a řádky</b>: pero-ocr, model pero_eu_cz_print_newspapers_2022-09-26 (PAGE XML, ALTO).", STY["body"]),
             Paragraph("2. <b>Bloky</b>: YOLO model TextBite (yolo-m-1200), třídy <i>title</i> / <i>text</i>; "
                       "řádky mimo YOLO bloky jsou shlukovány do doplňkových bloků (čárkovaně).", STY["body"]),
             Paragraph("3. <b>Pořadí čtení</b>: rekurzivní XY-cut nad bloky (záhlaví strany první, svislé řezy "
                       "v mezisloupcových mezerách, vodorovné jen u pásů přes více sloupců). "
                       "<b>Vodorovné čáry</b> přes ≥ 2 sloupce (i jen přes část strany) se detekují z obrazu; "
                       "každá buď otevírá sekci čtenou až po zbytku strany (např. fejeton pod čarou), nebo je "
                       "lokálním oddělovačem, nebo se ignoruje. Volbu pro každou čáru určuje <b>skóre dělených "
                       "slov</b>: blok končící spojovníkem, po němž následuje blok začínající malým písmenem (+1), "
                       "nebo nadpis / velké písmeno (−1).", STY["body"]),
             Paragraph("4. <b>Sloupce</b>: profil pokrytí osy x řádky užšími než 55 % šířky strany, mezery = výrazná minima profilu.", STY["body"]),
             Paragraph("5. <b>Odstavce</b>: dělení bloků podle odsazení prvního řádku, krátkého předchozího řádku "
                       "a větší svislé mezery (nikdy uvnitř děleného slova); spojení řádků se slučováním dělených slov. "
                       "<b>Přetékání</b>: odstavec pokračuje do dalšího bloku, sloupce i strany, když končí spojovníkem "
                       "a pokračování začíná malým písmenem, když věta neskončila a další blok začíná malým písmenem, "
                       "nebo když je poslední řádek plný a další blok začíná bez odsazení (nadpis mezi nimi spojení ruší).",
                       STY["body"]),
             Spacer(1, 8)]
    rows = [["strana", "uuid", "sloupce", "čáry", "bloky", "odstavce", "řádky", "znaky", "děl. slova ✓/✗"]]
    for p in pages:
        s = p["stats"]
        rows.append([p["page_no"], p["uuid"][:8], s["columns"], s.get("rules", 0), s["blocks"], s["paragraphs"],
                     s["lines"], s["chars"], f"{s.get('hyphen_ok', 0)}/{s.get('hyphen_broken', 0)}"])
    t = Table(rows)
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "DV", 9), ("FONT", (0, 0), (-1, 0), "DVB", 9),
                           ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee"))]))
    joined = [L for L in logical.values() if len(L["parts"]) > 1]
    story += [t, Spacer(1, 6),
              Paragraph(f"Logických odstavců: {len(logical)}, z toho přetéká do dalšího bloku/sloupce: {len(joined)}, "
                        f"přes stranu: {sum(len(L['pages']) > 1 for L in logical.values())}.", STY["body"]),
              Spacer(1, 6),
              Paragraph("Každá strana má v PDF tři pohledy: (a) layout a pořadí čtení, (b) odstavce a řádky, "
                        "(c) přepis textu. Obrazové stránky obsahují neviditelnou textovou vrstvu (lze hledat a kopírovat).",
                        STY["body"])]
    flow(c, story, "Přehled", "intro", level=0)


def load_pages(results):
    """page JSONs written by analyze_layout.py, in page order"""
    pages = [json.loads(f.read_text()) for f in Path(results).glob("*.json") if f.name != "flow.json"]
    return sorted(pages, key=lambda p: p["page_no"])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--order", type=Path, help="(ignored, page order is taken from the results)")
    ap.add_argument("--results", required=True, type=Path)
    ap.add_argument("--images", required=True, type=Path, help="dir with page images <uuid>.jpg")
    ap.add_argument("-o", "--output", required=True, type=Path)
    ap.add_argument("--meta", type=Path, help="meta.json from prepare_issues.py (title, date)")
    ap.add_argument("--title", default=None)
    args = ap.parse_args()
    if args.title is None:
        if args.meta and args.meta.exists():
            m = json.loads(args.meta.read_text())
            y, mo, d = (m["date"].split("-") + ["", "", ""])[:3]
            args.title = f"{m['title']}, {int(d)}. {int(mo)}. {y} – OCR a layout" if d else f"{m['title']} – OCR a layout"
        else:
            args.title = "OCR a layout"

    pages = load_pages(args.results)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(args.output), pagesize=A4)
    c.setTitle(args.title)
    c.setAuthor("layout pipeline")
    c.showOutline()
    flow_file = args.results / "flow.json"
    logical = {L["id"]: L for L in json.loads(flow_file.read_text())} if flow_file.exists() else {}
    pindex = {p["id"]: (pg["page_no"], p) for pg in pages for b in pg["blocks"] for p in b["paragraphs"]}
    intro(c, pages, args.title, logical)
    for page in pages:
        img = load_image(args.images / page["image"])
        layout_page(c, page, img)
        para_page(c, page, img, pindex)
        text_pages(c, page, logical, pindex)
    c.save()
    print(f"written {args.output}")


if __name__ == "__main__":
    main()
