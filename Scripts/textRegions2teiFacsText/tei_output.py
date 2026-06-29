import xml.etree.ElementTree as ET
from lxml import etree
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from copy import deepcopy

from .line_ana import LineAna, LineEndCat, Y

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NSMAP = {None: TEI_NS, "xml": XML_NS}
xpath_ns = {"tei": TEI_NS}

class TEIOutput:
  tei_id: str
  TEI: etree
  texts: list = [] # nested list with pb/cb/lb
  paragraphs: list = [] # list with paragraphs
  surfaces: list = [] # list with surfaces that contains zones in childs
  surfaces_url_to_index: dict = {}
  
  paragraphs_i: int = 0
  
  texts_ptr: list = [0, 0, 0]  # ( pb, cb, lb)
  zones_ptr: list = [0, 0, 0, 0]  # ( surface, area, col, line)

  zone_pb: dict = None
  zone_cb: dict = None
  zone_lb: dict = None

  box2attrib = staticmethod(lambda b: {
    "ulx": str(b[0]),
    "uly": str(b[1]),
    "lrx": str(b[2]),
    "lry": str(b[3]),
  }) 

  points2attrib = staticmethod(lambda points: {
    "points": " ".join(f"{x},{y}" for x, y in points)
  } if len(points) > 0 else {})

  merge_boxes = staticmethod(lambda childs: (
    min(c.get("bbox_xyxy", (0,0,0,0))[0] for c in childs),
    min(c.get("bbox_xyxy", (0,0,0,0))[1] for c in childs),
    max(c.get("bbox_xyxy", (0,0,0,0))[2] for c in childs),
    max(c.get("bbox_xyxy", (0,0,0,0))[3] for c in childs),
   ))

  
  hull_from_boxes = staticmethod(lambda boxes: 
     TEIOutput.hull_from_points(np.array(
        [ (b[0], b[1]) for b in boxes ] 
        + [ (b[0], b[3]) for b in boxes ]
        + [ (b[2], b[1]) for b in boxes ]
        + [ (b[2], b[3]) for b in boxes ]
     )) 
   ) 
  hull_from_points = staticmethod(lambda points:
     points[ConvexHull(points).vertices]
   )
  
  @staticmethod
  def hull_from_zones(zones):
    """
    zones: list of dict
        zone["bounding_polygon_points"] -> [(x,y), ...]  (preferred)
        zone["bbox_xyxy"] -> [x1,y1,x2,y2]  (fallback)

    returns: list of (x,y) forming convex hull (CCW order)
    """
    all_points = []

    for z in zones:
        if "bounding_polygon_points" in z:
            all_points.extend(tuple(p) for p in z["bounding_polygon_points"])
            print(f"INFO: using bounding_polygon_points for zone {z.get('id','unknown')}, points: {z['bounding_polygon_points']}")    
        elif "bbox_xyxy" in z and z["bbox_xyxy"]:
            x1, y1, x2, y2 = z["bbox_xyxy"]
            all_points.extend([
                (x1, y1),
                (x2, y1),
                (x2, y2),
                (x1, y2),
            ])

    if not all_points:
        return []

    return TEIOutput.hull_from_points(np.array(all_points))

  break_no = staticmethod(lambda endType: 
    {"break": "no"} if endType == LineEndCat.HYPHEN else {}
  )

  def __init__(self, tei_id):
    self.tei_id = tei_id
    self.TEI = etree.Element(
      "{%s}TEI" % TEI_NS,
      nsmap=NSMAP,
      attrib={
        "{%s}lang" % XML_NS: "cs",
        "{%s}id" % XML_NS: tei_id,
      }
    )
    # facsimile
    self.facsimile = etree.SubElement(self.TEI, "{%s}facsimile" % TEI_NS)
    # text/body
    self.text = etree.SubElement(self.TEI, "{%s}text" % TEI_NS)
    self.body = etree.SubElement(self.text, "{%s}body" % TEI_NS)

    self.el_ptr = self.body
    self.parent_el_ptr = self.body
    self.prev_line_end_type = LineEndCat.UNKNOWN
  
  def add_path(self, points, orientation, thickness, surface_url):
    surface = self.surfaces[self.surfaces_url_to_index[surface_url]]
    path_el = etree.SubElement(
      surface["element"], 
      "{%s}path" % TEI_NS, 
      attrib={
        "points": " ".join(f"{x},{y}" for x, y in points),
        "type": orientation,
        "n": str(thickness),
      }
    )
  def add_zone(self, zone, zone_type, surface_url):
    """
      add general zone as a direct child of surface, without reference from text (pb/cb/lb)
       - useful for zones that are not directly connected to text (e.g. decorations, marginal 
    """
    if not surface_url in self.surfaces_url_to_index:
      print(f"WARN: surface url {surface_url} not found for zone {zone.get('id','unknown')}, skipping zone")
      return
    surface = self.surfaces[self.surfaces_url_to_index[surface_url]]
    f_area = etree.SubElement(
      surface["element"], 
      "{%s}zone" % TEI_NS, 
      attrib={
        "type": zone_type,
        **TEIOutput.points2attrib(zone.get("bounding_polygon_points", [])),
        **TEIOutput.box2attrib(zone.get("bbox_xyxy", (0,0,0,0))),
        }
      )

  def add_region(self, region):
    if region.get("is_page_start"):
      pb = self.start_new_page(region["page_n"], region["page_meta"])
      self.el_ptr = pb
    if region.get("is_column_start"):
      cb = self.start_new_column(region["col_n"])
      self.lines_in_column = 0
      self.el_ptr = cb
    for line in region['region_content'].get('lines', []):
      if not line.get("text", None):
        # print(f"WARN: line without text, skipping: {line}")
        continue
      # insert paragraph if not present or if it begins
      self.lines_in_column += 1
      if self.prev_line_end_type != LineEndCat.HYPHEN:
        if not self.el_ptr.tail:
          self.el_ptr.tail = ""
        self.el_ptr.tail += "\n"
      lb = self.start_new_line(line)
      self.el_ptr = lb
      self.insert_line_text(line)



  def start_new_page(self, page_n, page_meta):
    self.close_current_page()
    print(f"INFO: start page {page_n} with meta {page_meta}")
    # whole page corresponds to a surface
    if not page_meta.get("url","") in self.surfaces_url_to_index:
      self.surfaces_url_to_index[page_meta["url"]] = len(self.surfaces)
      f_pg_id = f"{self.tei_id}.f.pg{page_n}"
      f_pg = etree.SubElement(
        self.facsimile,
        "{%s}surface" % TEI_NS, 
        attrib={
          "{%s}id" % XML_NS: f_pg_id,
          "n": str(page_n),
          "ulx": "0",
          "uly": "0",
          "lrx": str(page_meta.get("width",0)), 
          "lry": str(page_meta.get("height",0))
          }
        )
      etree.SubElement(
        f_pg,
        "{%s}graphic" % TEI_NS, 
        attrib={
          "url": page_meta["url"]
          }
        )
      self.surfaces.append({
        "element": f_pg,
        "id": f_pg_id,
        "areas_cnt": 0,
        "url": page_meta["url"],
        "width": page_meta.get("width",0),
        "height": page_meta.get("height",0),
        "childs": [],
      })
      self.zones_ptr = [len(self.surfaces), 0, 0, 0]

    pb_id = f"{self.tei_id}.pb{self.texts_ptr[0] + 1}"
    surface = self.surfaces[self.surfaces_url_to_index[page_meta["url"]]]
    surface["areas_cnt"] += 1
    # create zone for area
    f_area_id = f"{surface['id']}.a{surface['areas_cnt']}"
    pb = etree.SubElement(
      self.parent_el_ptr,
      "{%s}pb" % TEI_NS, 
      attrib={
        "{%s}id" % XML_NS: pb_id,
        **TEIOutput.break_no(self.prev_line_end_type),
        "n": str(page_n),
        "facs": f"#{f_area_id}"
        }
      )
    self.texts.append({
      "element": pb,
      "id": pb_id,
      "childs": [],
    })
    self.texts_ptr = [len(self.texts), 0, 0]

    f_area = etree.SubElement(
      surface["element"], 
      "{%s}zone" % TEI_NS, 
      attrib={
        "{%s}id" % XML_NS: f_area_id,
        "start": f"#{pb_id}",
        "type": "page",
        }
      )
    self.zone_pb = {
      "element": f_area,
      "id": f_area_id,
      "cols_cnt": 0,
      "childs": [],
    }
    surface["childs"].append(self.zone_pb)
    self.zones_ptr = [self.zones_ptr[0], len(surface["childs"]), 0, 0]
    return pb

  def close_current_page(self):
    if not self.zone_pb:
      return
    self.close_current_column()
    
    points = TEIOutput.hull_from_zones(self.zone_pb["childs"])
    self.zone_pb["bounding_polygon_points"] = points
    print (f"INFO: page {self.zone_pb['id']} hull points: {points}")
    print (f"INFO: page childs {[c.get('bbox_xyxy', (0,0,0,0)) for c in self.zone_pb['childs']]}")
    self.zone_pb["element"].attrib.update(TEIOutput.points2attrib(points))

    bbox_xyxy = TEIOutput.merge_boxes(self.zone_pb["childs"])
    self.zone_pb["bbox_xyxy"] = bbox_xyxy
    self.zone_pb["element"].attrib.update(TEIOutput.box2attrib(bbox_xyxy))
    
    self.zone_pb = None

  def remove_last_hyphen_if_present(self):
    # remove last hyphen (pc with break=no) in all paragraphs, if present, as it is likely an artifact of line merging and not a real hyphen
    for pc in self.TEI.xpath(".//tei:*[last()][local-name()='pc'][@force='weak']", namespaces=xpath_ns):
      parent = pc.getparent()
      if parent is not None and not pc.tail:
        parent.text += pc.text if parent.text else pc.text
        parent.remove(pc)

  def start_new_column(self, col_n):
    self.close_current_column()
    txt = self.texts[self.texts_ptr[0] - 1]
    self.texts_ptr[1] += 1
    cb_id = f"{txt['id']}.cb{self.texts_ptr[1]}"
    zone = self.surfaces[self.zones_ptr[0] - 1]["childs"][self.zones_ptr[1] - 1]
    ### zone["cols_cnt"] += 1
    self.zones_ptr[2] += 1
    f_col_id = f"{zone['id']}.c{self.zones_ptr[2]}"
    cb = etree.SubElement(
      self.parent_el_ptr, 
      "{%s}cb" % TEI_NS, 
      attrib={
        "{%s}id" % XML_NS: cb_id,
        **TEIOutput.break_no(self.prev_line_end_type),
        "facs": f"#{f_col_id}",
        }
      )
    txt["childs"].append({
      "element": cb,
      "id": cb_id,
      "childs": [],
    })
    self.texts_ptr[2] = 0
    f_col = etree.SubElement(
      zone["element"], 
      "{%s}zone" % TEI_NS, 
      attrib={
        "{%s}id" % XML_NS: f_col_id,
        "start": f"#{cb_id}",
        "type": "column",
        }
      )
    self.zone_cb = {
      "element": f_col,
      "id": f_col_id,
      "lines_cnt": 0,
      "childs": [],
    }
    zone["childs"].append(self.zone_cb)
    self.zones_ptr[3] = 0
    return cb

  def close_current_column(self):
    if not self.zone_cb:
      return
    
    points = TEIOutput.hull_from_zones(self.zone_cb["childs"])
    self.zone_cb["bounding_polygon_points"] = points
    self.zone_cb["element"].attrib.update(TEIOutput.points2attrib(points))

    
    bbox_xyxy = TEIOutput.merge_boxes(self.zone_cb["childs"])
    self.zone_cb["bbox_xyxy"] = bbox_xyxy
    self.zone_cb["element"].attrib.update(TEIOutput.box2attrib(bbox_xyxy))
    self.zone_cb = None  

  def start_new_line(self, line):
    txt = self.texts[self.texts_ptr[0] - 1]["childs"][self.texts_ptr[1] - 1]
    self.texts_ptr[2] += 1
    lb_id = f"{txt['id']}.lb{self.texts_ptr[2]}"
    zone = self.surfaces[self.zones_ptr[0] - 1]["childs"][self.zones_ptr[1] - 1]["childs"][self.zones_ptr[2] - 1]
    self.zones_ptr[3] += 1
    f_line_id = f"{zone['id']}.l{self.zones_ptr[3]}"

    lb = etree.SubElement(
      self.parent_el_ptr, 
      "{%s}lb" % TEI_NS, 
      attrib={
        "{%s}id" % XML_NS: lb_id, 
        **TEIOutput.break_no(self.prev_line_end_type),
        "facs": f"#{f_line_id}",
        }
      )
    txt["childs"].append({
      "element": lb,
      "id": lb_id,
    })
    self.texts_lb_n = len(txt["childs"])
    f_line = etree.SubElement(
      zone["element"], 
      "{%s}zone" % TEI_NS, 
      attrib={
        "{%s}id" % XML_NS: f_line_id,
        "start": f"#{lb_id}",
        "type": "line",
        **TEIOutput.points2attrib(line.get("bounding_polygon_points", [])),
        **TEIOutput.box2attrib(line.get("bbox_xyxy", (0,0,0,0))),
        }
      )
    self.zone_lb = {
      "element": f_line,
      "id": f_line_id,
      "bbox_xyxy": line.get("bbox_xyxy", (0,0,0,0)),
      "bounding_polygon_points": line.get("bounding_polygon_points", None),
    }
    zone["childs"].append(self.zone_lb)
    self.zones_lb_n = len(zone["childs"])
    return lb
  
  def insert_line_text(self, line):
      text = line.get('text','')
      pc_hyphen= ''
      if line.get('ana', LineAna).lineEnd == LineEndCat.HYPHEN:
        text = line.get('text',' ')[:-1]
        pc_hyphen = line.get('text',' ')[-1]
      if etree.QName(self.parent_el_ptr).localname != 'p':
        self.p_id = f"{self.tei_id}.p{len(self.paragraphs)+1}"
        p = etree.SubElement(self.parent_el_ptr, "{%s}p" % TEI_NS, attrib={"{%s}id" % XML_NS: self.p_id})
        self.paragraphs.append({
          "element": p,
          "id": self.p_id,
        })
        self.parent_el_ptr = p
        # inserting first text in paragraph
        p.text = text
      else:
        # appending
        self.el_ptr.tail = text
      if line.get('ana', LineAna).lineEnd == LineEndCat.HYPHEN:
        if line.get('ana', LineAna).parEnd != Y:
          pc = etree.SubElement(self.parent_el_ptr, "{%s}pc" % TEI_NS, attrib={"force": "weak"})
          pc.text = pc_hyphen
          self.el_ptr = pc
        else:
          self.el_ptr.tail += pc_hyphen

      # print(f"INFO: line text {line.get('text','')}")
      if line.get('ana', LineAna).parEnd == Y: # paragraph end -> close paragraph
        self.parent_el_ptr = self.parent_el_ptr.getparent()
      self.prev_line_end_type = line.get('ana', LineAna).lineEnd
  
  def write(self, outTextFile, outFacsFile):
    Path(outTextFile).parent.mkdir(parents=True, exist_ok=True)
    Path(outFacsFile).parent.mkdir(parents=True, exist_ok=True)
    text_root = deepcopy(self.TEI)
    facs_root = deepcopy(self.TEI)
    # Remove facsimile from text copy
    facsimile = text_root.find("tei:facsimile", namespaces=xpath_ns)
    if facsimile is not None:
        facsimile.getparent().remove(facsimile)
    text = facs_root.find("tei:text", namespaces=xpath_ns)
    if text is not None:
        text.getparent().remove(text)

    etree.ElementTree(text_root).write(
        outTextFile,
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=True,
    )

    etree.ElementTree(facs_root).write(
        outFacsFile,
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=True,
    )

    print(f"INFO: text written to {outTextFile}")
    print(f"INFO: facsimile written to {outFacsFile}")