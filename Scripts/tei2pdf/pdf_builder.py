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

  def build_pdf(self, output_path: str, max_dim=1500):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    self.c = canvas.Canvas(str(output_path))
    parser = ET.XMLParser(remove_blank_text=True, no_network=True, recover=True)
    tree = ET.parse(str(self.tei_path), parser)
    root = tree.getroot()
    tei_id = root.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
    # loop over facsimiles/surface elements and add each image to the PDF
    for surface in root.findall(".//{http://www.tei-c.org/ns/1.0}surface"):
        surface_id = surface.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
        graphic = surface.find("{http://www.tei-c.org/ns/1.0}graphic")
        self.initialize_page(surface)
        if graphic is not None:
          self.draw_image(graphic, tei_id, surface_id, position=[(0,0)], max_dim=max_dim)
        
        zones = surface.xpath(".//tei:zone", namespaces=ns)
        facs_ids = {
          el.get("facs")[1:]: el
          for el in root.xpath(".//tei:*[@facs]", namespaces=ns)
          if el.get("facs", "").startswith("#")
        }

        for zone in zones:
          zid = zone.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
          pos = [(0, 0)]
          if zid in facs_ids:
            pos.append((1, 0)) # draw second time on the right side for better visibility
          else:
            pos.append((2, 0)) # draw third time even further right if not linked to any text element to avoid overlap with text
          self.draw_zone(zone, position=pos)

        for path in surface.xpath(".//tei:path", namespaces=ns):
          self.draw_path(path, position=[(0,0),(2,0)])
        
        
        ################## TODO:
       

        zone_lookup = { 
          zone.attrib.get("{http://www.w3.org/XML/1998/namespace}id"): zone 
          for zone 
          in surface.findall(".//{http://www.tei-c.org/ns/1.0}zone") 
          if zone.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
        }

        previous_line_zone = None
        pending_page_break = False
        pending_column_break = False
        for elem in root.xpath(".//tei:pb | .//tei:lb | .//tei:cb", namespaces=ns):
            if not elem.get("facs") or elem.get("facs").lstrip("#") not in zone_lookup:
              continue
            
            if elem.tag.endswith("pb"):
              self.draw_beginning(elem, zone_lookup[elem.get("facs").lstrip("#")],position=[(0,0), (1,0)])
              pending_page_break = True
              if previous_line_zone is not None:
                self.draw_arrow(previous_line_zone,(self.page_width,self.page_height,self.page_width,self.page_height),position=[(1,0)]) # arrow from last line to right edge of page
              continue

            if elem.tag.endswith("cb"):
              self.draw_beginning(elem, zone_lookup[elem.get("facs").lstrip("#")],position=[(0,0), (1,0)])
              pending_column_break = True
              continue
        
            if elem.tag.endswith("lb"):
                zone_id = elem.get("facs")
                if not zone_id:
                    continue
        
                zone = zone_lookup[zone_id.lstrip("#")]
                ulx, uly, lrx, lry = get_zone_box(zone)
        
                # convert TEI coords - PDF coords
                y_top = self.page_height - uly
                y_bottom = self.page_height - lry
        
                # compute anchor points
                start_x = lrx
                start_y = (y_top + y_bottom) / 2
                if pending_page_break:
                  previous_line_zone = (0,0,0,0) # anchor from left edge of page
                  pending_page_break = False
                if pending_column_break and previous_line_zone is not None:
                    # draw arrow from previous line to this line
                    self.draw_arrow(previous_line_zone, (ulx, uly, lrx, lry), position=[(1,0)]) # arrow from last line to this line        
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
          pdf_y = self.page_height - lry

          # Optional: scale font to line height
          font_size = fit_text_to_box(self.c, text, width, height, font_name="DejaVu", max_font_size=height, min_font_size=3)
          self.c.setFont("DejaVu", font_size)
          self.c.setFillColor(colors.black)

          text_width = pdfmetrics.stringWidth(text, "DejaVu", font_size)
          # Center horizontally
          x = ulx + (width - text_width) / 2
          # Vertically center baseline
          y = self.page_height - uly - (height - font_size) / 2 - font_size

          # Draw text
          self.c.drawString(x+self.page_width, y, text)

        self.c.showPage()
            
    self.c.save()


  def draw_arrow(self, start_zone, end_zone, position=[(0,0)]):
    start_x = start_zone[2]
    start_y = self.page_height - start_zone[3]
    end_x = end_zone[0]
    end_y = self.page_height - end_zone[1]
    for pos in position:
      self.c.setStrokeColor(ZONE_COLORS.get("column", colors.black))
      self.c.setLineWidth(1)
      draw_arrow(self.c, start_x+pos[0]*self.page_width, start_y+pos[1]*self.page_height,
                      end_x+pos[0]*self.page_width, end_y+pos[1]*self.page_height)

  def draw_image(self, graphic, tei_id, surface_id, position=[(0,0)], max_dim=1500):
    url = graphic.get("url") 
    if url and Path(url).suffix.lower() in IMAGE_EXTENSIONS:
        cached_image = get_cached_image(url, self.cache_dir, tei_id, surface_id)
        img = Image.open(cached_image)
        ratio = min(max_dim / self.page_width, max_dim / self.page_height, 1)
        new_size = (int(self.page_width * ratio), int(self.page_height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
        #img = img.convert("L")  # grayscale
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=80, optimize=True, progressive=True)
        buffer.seek(0)
        for pos in position:       
          self.c.drawImage(ImageReader(buffer), 0+pos[0]*self.page_width, 0+pos[1]*self.page_height, width=self.page_width, height=self.page_height)


  def initialize_page(self, surface, x_stretch=3, y_stretch=1):
    #self.page_width, self.page_height = self.get_max_dimensions(surface)
    self.page_width = float(surface.get("lrx", 0))
    self.page_height = float(surface.get("lry", 0))
    self.c.setPageSize((self.page_width * x_stretch, self.page_height * y_stretch))
    self.c.setFillColor(colors.white)
    self.c.rect(0, 0, self.page_width * x_stretch, self.page_height * y_stretch, fill=1)


  def get_max_dimensions(self, surface):
    max_width = 0
    max_height = 0

    for el in surface.xpath(".//tei:*[@ulx][@uly][@lrx][@lry] | .//tei:*[@points]", namespaces=ns):
      try:
        ulx = float(el.get("ulx", 0))
        uly = float(el.get("uly", 0))
        lrx = float(el.get("lrx", 0))
        lry = float(el.get("lry", 0))

        max_width = max(max_width, lrx)
        max_height = max(max_height, lry)
      except (TypeError, ValueError):
        pass
      
      try:
        points_attr = el.get("points")
        if points_attr:
          for pair in points_attr.strip().split():
              x_str, y_str = pair.split(",")
              x = float(x_str)
              y = float(y_str)

              max_width = max(max_width, x)
              max_height = max(max_height, y)
      except (TypeError, ValueError):
        pass

    return max_width, max_height

  def draw_beginning(self, elem, zone, position=[(0,0)]):
    ulx, uly, lrx, lry = get_zone_box(zone)
    ztype = zone.get("type")
    self.c.setStrokeColor(ZONE_COLORS.get(ztype, colors.red))
    self.c.setLineWidth(ZONE_LINE_WIDTH.get(ztype, 4))
    self.c.setDash(ZONE_LINE_DASH.get(ztype, []))
    self.draw_point(ulx, uly, position)
  
  def draw_point(self, x, y, position=[(0,0)], size=10):
    for pos in position:
      self.c.circle(x+pos[0]*self.page_width, self.page_height - y+pos[1]*self.page_height, size, stroke=1, fill=1)
  def draw_zone(self, zone, position=[(0,0)]):
    points = self.get_zone_bounds(zone)
    ztype = zone.get("type")
    for pos in position:
      if len(points) >= 2:
        path = self.c.beginPath()
        path.moveTo(points[0][0]+pos[0]*self.page_width, self.page_height - points[0][1]+pos[1]*self.page_height)

        for p in points[1:]:
            path.lineTo(p[0]+pos[0]*self.page_width, self.page_height - p[1]+pos[1]*self.page_height)

        path.close()
        self.c.setStrokeColor(ZONE_COLORS.get(ztype, colors.black))
        self.c.setLineWidth(ZONE_LINE_WIDTH.get(ztype, 1))
        self.c.setDash(ZONE_LINE_DASH.get(ztype, []))
        self.c.drawPath(path, stroke=1, fill=0)


  def get_zone_bounds(self, zone):
    points = []
    points_attr = zone.get("points")
    if points_attr:
      for pair in points_attr.strip().split():
          x_str, y_str = pair.split(",")
          x = float(x_str)
          y = float(y_str)
          points.append((x, y))
    else:
      ulx = zone.get("ulx")
      uly = zone.get("uly")
      lrx = zone.get("lrx")
      lry = zone.get("lry")
      if None not in (ulx, uly, lrx, lry):
        ulx = float(ulx)
        uly = float(uly)
        lrx = float(lrx)
        lry = float(lry)
        points.append((ulx, uly))
        points.append((lrx, uly))
        points.append((lrx, lry))
        points.append((ulx, lry))
    return points
  
  def draw_path(self, path, position=[(0,0)]):
    ptype = path.get("type", "unknown")
    points_attr = path.get("points")
    thickness = max(1, int(float(path.get("n", 1))))
    for pos in position:
      if points_attr:
        pts = []
        for pair in points_attr.strip().split():
          x_str, y_str = pair.split(",")
          x = float(x_str)
          y = float(y_str)
          # Convert TEI top-left - PDF bottom-left
          pdf_y = self.page_height - y
          pts.append((x+pos[0]*self.page_width, pdf_y+pos[1]*self.page_height))
        if len(pts) >= 2:
          self.c.setStrokeColor(PATH_COLORS.get(ptype, colors.gray))
          self.c.setStrokeAlpha(0.2)
          self.c.setLineWidth(thickness)
          path_obj = self.c.beginPath()
          path_obj.moveTo(*pts[0])
          for p in pts[1:]:
              path_obj.lineTo(*p)
          self.c.drawPath(path_obj, stroke=1, fill=0)
    self.c.setDash() # reset to solid