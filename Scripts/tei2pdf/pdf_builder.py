from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from PIL import Image
import re

#import xml.etree.ElementTree as ET
from lxml import etree as ET

from pathlib import Path
import io
from reportlab.lib import colors



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

ns = {"tei": "http://www.tei-c.org/ns/1.0"}








def is_no_text_before_element(elem):
    current = elem
    prev = current.getprevious()
    while prev is not None:
      if prev.tail and prev.tail.strip():
        return False
      elif prev.text and prev.text.strip():
        return False
      else:
        prev = prev.getprevious()
    return True





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

  def __init__(self, tei_path: str, cache_dir: str | None, tasks=None, styles = {}):
    self.tei_path = tei_path
    self.cache_dir = Path(cache_dir) if cache_dir else None
    self.tasks = tasks
    max_x = 0
    max_y = 0
    for task in self.tasks:
        positions = task.get_positions()

        for pos in positions:
            x, y = pos
            max_x = max(max_x, x)
            max_y = max(max_y, y)

    self.repeat_x = max_x + 1
    self.repeat_y = max_y + 1
    self.styles = styles


  def build_pdf(self, output_path: str):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    self.c = canvas.Canvas(str(output_path))
    parser = ET.XMLParser(remove_blank_text=True, no_network=True, recover=True)
    tree = ET.parse(str(self.tei_path), parser)
    root = tree.getroot()
    tei_id = root.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
    # loop over facsimiles/surface elements and add each image to the PDF
    for surface in root.findall(".//{http://www.tei-c.org/ns/1.0}surface"):
      surface_id = surface.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
      self.initialize_page(surface)
      for task in self.tasks:
        print(f"{task}: Running on surface {surface_id} of TEI document {tei_id}")
        task.run(self.c, 
                     surface, 
                     shared_context = {
                      "cache_dir": self.cache_dir,
                      "tei_id": tei_id,
                      "surface_id": surface_id,
                      "root": root,
                      "ns": ns,
                      "page_width": self.page_width,
                      "page_height": self.page_height,
                      "styles": self.styles
                     })
      self.c.showPage()
    self.c.save()

    return
    ##### TODO: REMOVE THIS HARDCODED TESTING CODE AND REPLACE WITH TASKS DEFINED IN YAML CONFIG #####
    max_dim = 1500
    # loop over facsimiles/surface elements and add each image to the PDF
    for surface in root.findall(".//{http://www.tei-c.org/ns/1.0}surface"):
        surface_id = surface.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
        graphic = surface.find("{http://www.tei-c.org/ns/1.0}graphic")
        self.initialize_page(surface)
        
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

        # draw paths in current surface
        for path in surface.xpath(".//tei:path", namespaces=ns):
          self.draw_path(path, position=[(0,0),(2,0)])
        
        # current surface id to zone mapping:
        zone_lookup = { 
          zone.attrib.get("{http://www.w3.org/XML/1998/namespace}id"): zone 
          for zone 
          in surface.findall(".//{http://www.tei-c.org/ns/1.0}zone") 
          if zone.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
        }

        # draw reading order for pb and cb
        order = [0,0]
        previous_line_zone = (0,0,0,0)
        pending_column_break = False
        for elem in root.xpath(".//tei:pb | .//tei:lb | .//tei:cb", namespaces=ns):
            if not elem.get("facs") or elem.get("facs").lstrip("#") not in zone_lookup:
              continue
            
            if elem.tag.endswith("pb"):
              order[0] += 1
              order[1] = 0
              self.draw_beginning(elem, zone_lookup[elem.get("facs").lstrip("#")],position=[(0,0), (1,0)])
              if previous_line_zone != (0,0,0,0):
                self.draw_arrow(previous_line_zone,(self.page_width,self.page_height,self.page_width,self.page_height),position=[(1,0),(2,0)], label=f"{''.join(map(str, order))}") # arrow from last line to right edge of page
                previous_line_zone = (0,0,0,0)
            elif elem.tag.endswith("cb"):
              order[1] += 1
              self.draw_beginning(elem, zone_lookup[elem.get("facs").lstrip("#")],position=[(0,0), (1,0)])
              pending_column_break = True
            elif elem.tag.endswith("lb"):
                zone_id = elem.get("facs")
                if not zone_id:
                    continue
                zone = zone_lookup[zone_id.lstrip("#")]
                ulx, uly, lrx, lry = get_zone_box(zone)
                if pending_column_break:  # and previous_line_zone != (0,0,0,0):
                    # draw arrow from previous line to this line
                    self.draw_arrow(previous_line_zone, (ulx, uly, lrx, lry), position=[(1,0),(2,0)], label=f"{''.join(map(str, order))}") # arrow from last line to this line        
                    pending_column_break = False
                previous_line_zone = (ulx, uly, lrx, lry)
        order[0] += 1
        order[1] = 0
        self.draw_arrow(previous_line_zone,(self.page_width,self.page_height,self.page_width,self.page_height),position=[(1,0),(2,0)], label=f"{''.join(map(str, order))}") # arrow from last line to right edge of page

        self.c.showPage()
            
    self.c.save()


  def draw_arrow(self, start_zone, end_zone, position=[(0,0)], label=None):
    start_x = start_zone[2]
    start_y = self.page_height - start_zone[3]
    end_x = end_zone[0]
    end_y = self.page_height - end_zone[1]
    for pos in position:
      #self.c.setStrokeColor(ZONE_COLORS.get("column", colors.black))
      self.c.setStrokeColor(colors.purple)
      self.c.setStrokeAlpha(0.5)
      self.c.setLineWidth(10)
      draw_arrow(self.c, start_x+pos[0]*self.page_width, start_y+pos[1]*self.page_height,
                      end_x+pos[0]*self.page_width, end_y+pos[1]*self.page_height)
      if label:
        self.c.setFont("DejaVu", 30)
        self.c.setFillColor(colors.red)
        self.c.drawString(0.1*start_x+0.9*end_x+pos[0]*self.page_width, 0.1*start_y+0.9*end_y+pos[1]*self.page_height, label)


  def initialize_page(self, surface):
    #self.page_width, self.page_height = self.get_max_dimensions(surface)
    self.page_width = float(surface.get("lrx", 0))
    self.page_height = float(surface.get("lry", 0))
    self.c.setPageSize((self.page_width * self.repeat_x, self.page_height * self.repeat_y))
    self.c.setFillColor(colors.white)
    self.c.rect(0, 0, self.page_width * self.repeat_x, self.page_height * self.repeat_y, fill=1)


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