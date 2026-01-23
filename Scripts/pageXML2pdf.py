import argparse
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from PIL import Image
import xml.etree.ElementTree as ET
from pathlib import Path
import json



pdfmetrics.registerFont(TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))

# --------------------
# PARAMETERS
# --------------------

IMAGE_EXTENSIONS = {".jpg", ".png", ".tif", ".tiff"}

PAGE_NS = {
    "p": "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
}

# --------------------
# ARGPARSE
# --------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert PAGE XML + images to a multipage searchable PDF"
    )

    parser.add_argument(
        "-i", "--images",
        required=True,
        type=Path,
        help="Directory containing page images"
    )

    parser.add_argument(
        "-x", "--xml",
        required=True,
        type=Path,
        help="Directory containing PAGE XML files"
    )

    parser.add_argument(
        "-j", "--jsonl",
        required=True,
        type=Path,
        help="JSONL file with page order (using uuid column to determine filename)"
    )

    parser.add_argument(
        "-o", "--output",
        required=True,
        type=Path,
        help="Output PDF file"
    )

    return parser.parse_args()

# --------------------
# MAIN
# --------------------
def main():
    args = parse_args()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(args.output))
    with open(str(args.jsonl), newline="", encoding="utf-8") as f:
      for line in f:
        row = json.loads(line)
        img_path= args.images / f"{row['uuid_path']}.jpg"
        if not img_path.exists():
            print(f"Missing IMG for "+row["uuid"]+", skipping")
            continue

        xml_path = args.xml / f"{row['uuid']}.xml"
        if not xml_path.exists():
            print("Missing XML for "+row["uuid"]+", skipping")
            continue

        # Load image
        img = Image.open(img_path)
        w, h = img.size

        c.setPageSize((w, h))
        c.drawImage(str(img_path), 0, 0, w, h)

        # Parse PAGE XML
        with open(xml_path, encoding="utf-8") as f:
          tree = ET.parse(f)
        root = tree.getroot()
        
        
        ir = 0
        for region in root.findall(".//p:TextRegion", PAGE_NS):
          c.setFillColorRGB(0, 0.5, 0.5)
          coords_reg = region.find("p:Coords", PAGE_NS)
          coords = [tuple(map(int, p.split(","))) for p in coords_reg.attrib["points"].split()]
          xs = [p[0] for p in coords]
          ys = [p[1] for p in coords]
          # flip Y for PDF coordinate system
          coords = [(x_, h - y_) for x_, y_ in coords]
          # Create a path
          path = c.beginPath()
          x0, y0 = coords[0]
          path.moveTo(x0, y0)
          for x1, y1 in coords[1:]:
              path.lineTo(x1, y1)
          path.close()  # close polygon

          # Stroke the polygon (no fill)
          c.setStrokeColorRGB(0, 0, 1) 
          c.setLineWidth(5)
          c.drawPath(path, stroke=1, fill=0)
          
          ## print order
          font_name = "DejaVu"
          font_size = 10
          c.setFont(font_name, font_size)

          bbox_width = max(xs) - min(xs)
          bbox_height = max(ys) - min(ys)
          text_width = stringWidth(str(ir), font_name, font_size)
          text_height = font_size  # approx vertical height
          x_scale = bbox_width / text_width if text_width > 0 else 1.0
          y_scale = bbox_height / text_height if text_height > 0 else 1.0
          c.saveState()
          c.translate(min(xs), h - max(ys))  # top-left corner of polygon
          c.scale(min(x_scale, y_scale),min(x_scale, y_scale))                
          c.drawString(0, 0, str(ir))
          c.restoreState()
          ir += 1
          ###

          for line in region.findall(".//p:TextLine", PAGE_NS):
            c.setFillColorRGB(1, 0.5, 0)
            text_el = line.find(".//p:Unicode", PAGE_NS)
            coords_el = line.find("p:Coords", PAGE_NS)

            if text_el is None or coords_el is None:
                continue

            text = text_el.text
            if not text:
                continue


            coords = [tuple(map(int, p.split(","))) for p in coords_el.attrib["points"].split()]
            xs = [p[0] for p in coords]
            ys = [p[1] for p in coords]

            # flip Y for PDF coordinate system
            coords = [(x_, h - y_) for x_, y_ in coords]
            # Create a path
            path = c.beginPath()
            x0, y0 = coords[0]
            path.moveTo(x0, y0)
            for x1, y1 in coords[1:]:
                path.lineTo(x1, y1)
            path.close()  # close polygon

            # Stroke the polygon (no fill)
            c.setStrokeColorRGB(0, 1, 0) 
            c.setLineWidth(0.5)
            c.drawPath(path, stroke=1, fill=0)
            

            baseline_el = line.find("p:Baseline", PAGE_NS)
            if baseline_el is not None:
              baseline_y = sum(int(p.split(",")[1]) for p in baseline_el.attrib["points"].split()) / len(baseline_el.attrib["points"].split())
            else:
              baseline_y = min(ys)  # fallback: bottom of polygon
            baseline_offset = max(ys) - baseline_y

            # Draw text inside bounding box
            font_name = "DejaVu"
            font_size = 10
            c.setFont(font_name, font_size)

            bbox_width = max(xs) - min(xs)
            bbox_height = max(ys) - min(ys)
            text_width = stringWidth(text, font_name, font_size)
            text_height = font_size  # approx vertical height
            x_scale = bbox_width / text_width if text_width > 0 else 1.0
            y_scale = bbox_height / text_height if text_height > 0 else 1.0

            c.saveState()
            c.translate(min(xs), h - max(ys) + baseline_offset)  # top-left corner of polygon
            c.scale(x_scale, y_scale)                
            c.drawString(0, 0, text)
            c.restoreState()

        c.showPage()

    c.save()
    print(f"Saved multipage PDF to {args.output}")

# --------------------
# ENTRY POINT
# --------------------
if __name__ == "__main__":
    main()
