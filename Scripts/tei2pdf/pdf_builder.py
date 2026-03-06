from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from PIL import Image
#import xml.etree.ElementTree as ET
from lxml import etree as ET

from pathlib import Path
import io
from reportlab.lib import colors

from tei2pdf.image import get_cached_image


ZONE_COLORS = {
    "page": colors.red,
    "column": colors.blue,
    "line": colors.green,
    "": colors.black,
    "imageRegion": colors.orange,
    "outlayerLine": colors.purple,
    "textRegion": colors.brown
}
ZONE_LINE_WIDTH = {
    "page": 4,
    "column": 2,
    "line": 1,
    "": 1,
    "imageRegion": 3,
    "outlayerLine": 1,
    "textRegion": 2
}
ZONE_LINE_DASH = {
    "page": [],
    "column": [10, 5],
    "line": [8, 2],
    "": [],
    "imageRegion": [5, 5],
    "outlayerLine": [2, 2],
    "textRegion": []
}

PATH_COLORS = {
    "vertical": colors.darkcyan,
    "horizontal": colors.darkmagenta,
    "unknown": colors.gray
}

pdfmetrics.registerFont(TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
ns = {"tei": "http://www.tei-c.org/ns/1.0"}


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def get_lb_text(lb):
    """
    Returns all text between this <lb> and the next <lb>,
    including inline elements like <pc>.
    """

    parts = []

    # text directly after <lb/>
    if lb.tail:
        parts.append(lb.tail)

    # iterate over following siblings
    for sib in lb.itersiblings():
        # stop at next <lb>
        if sib.tag.endswith("lb"):
            break

        # element text
        if sib.text:
            parts.append(sib.text)

        # element tail
        if sib.tail:
            parts.append(sib.tail)

    return "".join(parts).strip()


def fit_text_to_box(c, text, box_width, box_height,
                    font_name="Helvetica",
                    max_font_size=20,
                    min_font_size=3):
    """
    Returns the largest font size that fits inside the box.
    """

    font_size = max_font_size

    while font_size >= min_font_size:
        text_width = pdfmetrics.stringWidth(text, font_name, font_size)
        text_height = font_size  # approx baseline height

        if text_width <= box_width and text_height <= box_height:
            return font_size

        font_size -= 0.5

    return min_font_size

def get_zone_box(zone):
    ulx = float(zone.get("ulx"))
    uly = float(zone.get("uly"))
    lrx = float(zone.get("lrx"))
    lry = float(zone.get("lry"))

    return ulx, uly, lrx, lry


from math import atan2, cos, sin, pi

def draw_arrow(c, x1, y1, x2, y2, head_len=20, head_angle=30):
    """
    Draw arrow from (x1, y1) to (x2, y2)
    """

    c.line(x1, y1, x2, y2)

    angle = atan2(y2 - y1, x2 - x1)

    angle1 = angle + pi - (head_angle * pi / 180)
    angle2 = angle + pi + (head_angle * pi / 180)

    x3 = x2 + head_len * cos(angle1)
    y3 = y2 + head_len * sin(angle1)

    x4 = x2 + head_len * cos(angle2)
    y4 = y2 + head_len * sin(angle2)

    c.line(x2, y2, x3, y3)
    c.line(x2, y2, x4, y4)




class PDFBuilder:
  def __init__(self, tei_path: str, cache_dir: str | None):
    self.tei_path = tei_path
    self.cache_dir = Path(cache_dir) if cache_dir else None

  def build_pdf(self, output_path: str):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output_path))
    parser = ET.XMLParser(remove_blank_text=True, no_network=True, recover=True)
    tree = ET.parse(str(self.tei_path), parser)
    root = tree.getroot()
    tei_id = root.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
    # loop over facsimiles/surface elements and add each image to the PDF
    for surface in root.findall(".//{http://www.tei-c.org/ns/1.0}surface"):
        surface_id = surface.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
        graphic = surface.find("{http://www.tei-c.org/ns/1.0}graphic")
        # draw background image if available, otherwise just create a blank page
        if graphic is not None:
            url = graphic.get("url")
            if url and Path(url).suffix.lower() in IMAGE_EXTENSIONS:
                cached_image = get_cached_image(url, self.cache_dir, tei_id, surface_id)
                img = Image.open(cached_image)
                page_width, page_height = img.size

                max_dim = 1500  # downscale constant
                ratio = min(max_dim / img.width, max_dim / img.height, 1)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.LANCZOS)
                #img = img.convert("L")  # grayscale
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=80, optimize=True, progressive=True)
                buffer.seek(0)       

                c.setPageSize((3*page_width, page_height)) # prevous size of image - before scaling
                c.drawImage(ImageReader(buffer), 0, 0, width=page_width, height=page_height)
        for zone in surface.findall(".//{http://www.tei-c.org/ns/1.0}zone"):
          ztype = zone.get("type")
          ulx = zone.get("ulx")
          uly = zone.get("uly")
          lrx = zone.get("lrx")
          lry = zone.get("lry")

          #Draw polygon if available
          points_attr = zone.get("points")
          for x_shift in (0, page_width): # draw each zone twice - on the image and on the right side for better visibility
            if points_attr:
              # Parse TEI points string → [(x, y), ...]
              pts = []
              for pair in points_attr.strip().split():
                  x_str, y_str = pair.split(",")
                  x = float(x_str)
                  y = float(y_str)
          
                  # Convert TEI top-left → PDF bottom-left
                  pdf_y = page_height - y
                  pts.append((x + x_shift, pdf_y))
          
              if len(pts) >= 2:
                  path = c.beginPath()
                  path.moveTo(*pts[0])
          
                  for p in pts[1:]:
                      path.lineTo(*p)
          
                  path.close()
                  c.setStrokeColor(ZONE_COLORS.get(ztype, colors.black))
                  c.setLineWidth(ZONE_LINE_WIDTH.get(ztype, 1))
                  c.setDash(ZONE_LINE_DASH.get(ztype, []))
                  c.drawPath(path, stroke=1, fill=0)
            elif not None in (ulx, uly, lrx, lry):
              ulx = float(ulx)
              uly = float(uly)
              lrx = float(lrx)
              lry = float(lry)
    
              width = lrx - ulx
              height = lry - uly
    
              # Convert TEI top-left → PDF bottom-left
              pdf_y = page_height - lry
    
              # Set color by type
              c.setStrokeColor(ZONE_COLORS.get(ztype, colors.blue))
              c.setLineWidth(ZONE_LINE_WIDTH.get(ztype, 10))
              c.setDash(ZONE_LINE_DASH.get(ztype, []))
              # Draw rectangle
              c.rect(ulx + x_shift, pdf_y, width, height, fill=0)        
        for path in surface.findall(".//{http://www.tei-c.org/ns/1.0}path"):
          ptype = path.get("type", "unknown")
          points_attr = path.get("points")
          thickness = max(1, int(float(path.get("n", 1))))
          if points_attr:
              pts = []
              for pair in points_attr.strip().split():
                  x_str, y_str = pair.split(",")
                  x = float(x_str)
                  y = float(y_str)
          
                  # Convert TEI top-left → PDF bottom-left
                  pdf_y = page_height - y
                  pts.append((x, pdf_y))
              if len(pts) >= 2:
                  c.setStrokeColor(PATH_COLORS.get(ptype, colors.gray))
                  c.setLineWidth(thickness)
                  path_obj = c.beginPath()
                  path_obj.moveTo(*pts[0])
                  for p in pts[1:]:
                      path_obj.lineTo(*p)
                  c.drawPath(path_obj, stroke=1, fill=0)
        
        c.setDash() # reset to solid
        zone_lookup = {}
        for zone in surface.findall(".//{http://www.tei-c.org/ns/1.0}zone"):
          zone_lookup[zone.attrib.get("{http://www.w3.org/XML/1998/namespace}id")] = zone

        previous_line_zone = None
        pending_column_break = False
        for elem in root.xpath(".//tei:lb | .//tei:cb", namespaces=ns):
            if not elem.get("facs") or elem.get("facs").lstrip("#") not in zone_lookup:
                continue
            if elem.tag.endswith("cb"):
                pending_column_break = True
                continue
        
            if elem.tag.endswith("lb"):
                zone_id = elem.get("facs")
                if not zone_id:
                    continue
        
                zone = zone_lookup[zone_id.lstrip("#")]
                ulx, uly, lrx, lry = get_zone_box(zone)
        
                # convert TEI coords → PDF coords
                y_top = page_height - uly
                y_bottom = page_height - lry
        
                # compute anchor points
                start_x = lrx
                start_y = (y_top + y_bottom) / 2
        
                if pending_column_break and previous_line_zone is not None:
                    # draw arrow from previous line to this line
        
                    prev_ulx, prev_uly, prev_lrx, prev_lry = previous_line_zone
                    prev_y_top = page_height - prev_uly
                    prev_y_bottom = page_height - prev_lry
        
                    arrow_start_x = prev_lrx
                    arrow_start_y = (prev_y_top + prev_y_bottom) / 2
        
                    arrow_end_x = ulx
                    arrow_end_y = (y_top + y_bottom) / 2
        
                    c.setStrokeColor(ZONE_COLORS.get("column", colors.black))
                    c.setLineWidth(1)

                    draw_arrow(c, arrow_start_x+page_width, arrow_start_y,
                                    arrow_end_x+page_width, arrow_end_y)
        
                    pending_column_break = False
        
                previous_line_zone = (ulx, uly, lrx, lry)



        line_zones = {}
        for zone in surface.findall(".//{http://www.tei-c.org/ns/1.0}zone[@type='line']"):
          zid = zone.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
          if not all(zone.get(a) for a in ("ulx", "uly", "lrx", "lry")):
            continue
          line_zones[zid] = {
            "ulx": float(zone.get("ulx")),
            "uly": float(zone.get("uly")),
            "lrx": float(zone.get("lrx")),
            "lry": float(zone.get("lry")),
          }
        for lb in root.findall(".//{http://www.tei-c.org/ns/1.0}lb"):
          facs = lb.get("facs")
          if not facs:
              continue
          facs_id = facs.lstrip("#")
          # Only print if zone belongs to this surface
          if facs_id not in line_zones:
              continue

          text = get_lb_text(lb)
          if not text:
              continue

          zone = line_zones[facs_id]

          ulx = zone["ulx"]
          uly = zone["uly"]
          lrx = zone["lrx"]
          lry = zone["lry"]

          width = lrx - ulx
          height = lry - uly

          # Convert coordinate system
          pdf_y = page_height - lry

          # Optional: scale font to line height
          font_size = fit_text_to_box(c, text, width, height, font_name="DejaVu", max_font_size=height, min_font_size=3)
          c.setFont("DejaVu", font_size)

          text_width = pdfmetrics.stringWidth(text, "DejaVu", font_size)
          # Center horizontally
          x = ulx + (width - text_width) / 2
          # Vertically center baseline
          y = page_height - uly - (height - font_size) / 2 - font_size

          # Draw text
          c.drawString(x+page_width, y, text)

        c.showPage()
            
    c.save()


