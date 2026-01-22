import argparse
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw
from pathlib import Path




# --------------------
# PARAMETERS
# --------------------


PAGE_NS = {
    "p": "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
}

STROKE_WIDTH = 3

COLORS = {
    "TextRegion": (255, 0, 0, 180),   # PAGE
    "TextLine": (0, 255, 0, 180),

    "TextBlock": (0, 0, 255, 180),    # ALTO
    "AltoTextLine": (255, 165, 0, 180),
    "AltoString": (255, 165, 0, 100),
    "AltoSP": (165, 0, 255, 255),

}

# --------------------

def parse_points_page(points_str):
    """PAGE: 'x,y x,y ...'"""
    return [tuple(map(int, p.split(","))) for p in points_str.split()]


def get_points_alto(elem, default=0):
    hpos = int(elem.attrib.get("HPOS", default))
    vpos = int(elem.attrib.get("VPOS", default))
    width = int(elem.attrib.get("WIDTH", default))
    height = int(elem.attrib.get("HEIGHT",default))
    return parse_points_alto(hpos, vpos, width, height)

def parse_points_alto(hpos, vpos, width, height):
    """ALTO: rectangle → polygon"""
    x, y = int(hpos), int(vpos)
    w, h = int(width), int(height)
    return [
        (x, y),
        (x + w, y),
        (x + w, y + h),
        (x, y + h),
        (x, y),
    ]

def get_bbox_alto(elem,default=0):
    """
    Given an ALTO element (TextLine, String, SP, etc.),
    return a bounding box suitable for PIL: (x0, y0, x1, y1)
    """
    hpos = int(elem.attrib.get("HPOS", default))
    vpos = int(elem.attrib.get("VPOS", default))
    width = int(elem.attrib.get("WIDTH", default))
    height = int(elem.attrib.get("HEIGHT",default))

    x0 = hpos
    y0 = vpos
    x1 = hpos + width
    y1 = vpos + height

    return (x0, y0, x1, y1)

def get_ns(tag):
    return tag.split("}")[0].strip("{")

# ---------- PAGE PARSER ----------
def draw_page(xml_path, output_png):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    NS = get_ns(root.tag)

    def ns(t): return f"{{{NS}}}{t}"

    page = root.find(f".//{ns('Page')}")
    width = int(page.attrib["imageWidth"])
    height = int(page.attrib["imageHeight"])

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    for region in root.iter(ns("TextRegion")):
        coords = region.find(ns("Coords"))
        if coords is None:
            continue
        pts = parse_points_page(coords.attrib["points"])
        draw.line(pts + [pts[0]], fill=COLORS["TextRegion"], width=STROKE_WIDTH)

    for line in root.iter(ns("TextLine")):
        coords = line.find(ns("Coords"))
        if coords is None:
            continue
        pts = parse_points_page(coords.attrib["points"])
        draw.line(pts + [pts[0]], fill=COLORS["TextLine"], width=STROKE_WIDTH)

    img.save(output_png)


# ---------- ALTO PARSER ----------
def draw_alto(xml_path, output_png):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    NS = get_ns(root.tag)

    def ns(t): return f"{{{NS}}}{t}"

    page = root.find(f".//{ns('Page')}")
    width = int(page.attrib["WIDTH"])
    height = int(page.attrib["HEIGHT"])

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    for block in root.iter(ns("TextBlock")):
        draw.line(get_points_alto(block), fill=COLORS["TextBlock"], width=STROKE_WIDTH)

        for line in block.iter(ns("TextLine")):
            draw.line(get_points_alto(line), fill=COLORS["AltoTextLine"], width=STROKE_WIDTH)

            for string in line.iter(ns("String")):
                draw.rectangle(get_bbox_alto(string), fill=COLORS["AltoString"], width=0)

            for sp in line.iter(ns("SP")):
                draw.rectangle(get_bbox_alto(sp,line.attrib.get("HEIGHT",0)), fill=COLORS["AltoSP"], width=0)
    img.save(output_png)



# --------------------
# ARGPARSE
# --------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert PAGE XML / ALTO XML / JSONL regions to png file with regions"
    )

    parser.add_argument(
        "-x", "--xml",
        type=Path,
        help="PageXML file to convert"
    )

    parser.add_argument(
        "-a", "--alto",
        type=Path,
        help="PageXML file to convert"
    )


    parser.add_argument(
        "-o", "--output",
        required=True,
        type=Path,
        help="Output PNG file"
    )

    args = parser.parse_args()
    if args.xml and args.alto:
        parser.error("Use only one of --xml or --alto")

    return args

# --------------------
# MAIN
# --------------------
def main():
    args = parse_args()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    if args.xml:
        draw_page(args.xml, args.output)
    elif args.alto:
        draw_alto(args.alto, args.output)

    print(f"Saved visualization to {args.output}")

# --------------------
# ENTRY POINT
# --------------------
if __name__ == "__main__":
    main()
