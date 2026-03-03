#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
import json
import xml.etree.ElementTree as ET
from decimal import Decimal
from scipy.spatial import ConvexHull
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from enum import Enum, auto
from typing import NamedTuple

class LineStartCat(Enum):
    UNKNOWN = auto()
    START = auto()
    START_NE = auto()
    MID = auto()
    PREV_HYPHEN = auto()

class LineEndCat(Enum):
    UNKNOWN = auto()
    END = auto()
    MID = auto()
    HYPHEN = auto()

class TriState(Enum):
    UNKNOWN = auto()
    NO = auto()
    YES = auto()


Y = TriState.YES
N = TriState.NO
U = TriState.UNKNOWN

def _tri(v):
    if v is True:
        return TriState.YES
    if v is False:
        return TriState.NO
    return TriState.UNKNOWN


class LineAna(NamedTuple):
    parStart: TriState = TriState.UNKNOWN
    parEnd: TriState = TriState.UNKNOWN
    lineStart: LineStartCat = LineStartCat.UNKNOWN
    lineEnd: LineEndCat = LineEndCat.UNKNOWN

    # --- helper methods for updating fields ---
    def with_parStart(self, value: TriState):
        return self._replace(parStart=value)
    def with_parStart(self, value: bool):
        return self._replace(parStart=_tri(value))

    def with_parEnd(self, value: TriState):
        return self._replace(parEnd=value)
    def with_parEnd(self, value: bool):
        return self._replace(parEnd=_tri(value))

    def with_lineStart(self, value: LineStartCat):
        return self._replace(lineStart=value)

    def with_lineEnd(self, value: LineEndCat):
        return self._replace(lineEnd=value)

    def annotate_line_start(self, ch, prevLine={}, prevCh={}):
        ana = LineStartCat.MID
        if ch.get("upper",None) and self.parStart == Y:
          ana = LineStartCat.START
        elif ch.get("upper",None) and prevCh.get("punct",None):
          ana = LineStartCat.START
        elif ch.get("upper",None):
          ana = LineStartCat.START_NE
        elif prevCh.get("hyphen",None) and self.parStart == N:
          ana = LineStartCat.PREV_HYPHEN
        elif self.parStart == Y:
          ana = LineStartCat.START
        return self.with_lineStart(ana)

    def annotate_line_end(self, ch, nextLine={}, nextCh={}):
        ana = LineEndCat.MID
        if self.parEnd == Y:
          ana = LineEndCat.END
        elif ch.get("hyphen",False) and self.parEnd == N:
          ana = LineEndCat.HYPHEN
        elif ch.get("hyphen",False) and nextLine.parStart == N:
          ana = LineEndCat.HYPHEN
        elif ch.get("punct",False) and self.parEnd == Y:
          ana = LineEndCat.END
        elif ch.get("punct",False) and nextLine.parStart == Y:
          ana = LineEndCat.END
        elif nextCh.get("upper",False) and self.parEnd == Y:
          ana = LineEndCat.END
        elif nextCh.get("upper",False) and nextLine.parStart == Y:
          ana = LineEndCat.END
        return self.with_lineEnd(ana)


def get_ns(el):
    return el.tag.split("}")[0].strip("{")
def get_name(el):
    return el.tag.split("}", 1)[1]

def ns(r,t):
  NS=get_ns(r)
  return f"{{{NS}}}{t}"

def parse_points_page(points_str):
    """PAGE: 'x,y x,y ...'"""
    return [tuple(map(int, p.split(","))) for p in points_str.split()]

def bbox_xyxy_from_points(points):
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return [ min(xs), min(ys), max(xs), max(ys) ]

def element_to_dict(el):
    data = dict(el.attrib)
    
    for child in el:
        tag = get_name(child)
        child_dict = element_to_dict(child)  # recurse

        # if the child has text but no children/attributes
        if not child_dict and (child.text and child.text.strip()):
            child_dict = child.text.strip()

        # handle multiple children with same tag
        if tag in data:
            if isinstance(data[tag], list):
                data[tag].append(child_dict)
            else:
                data[tag] = [data[tag], child_dict]
        else:
            data[tag] = child_dict

    return data

def convert_to_region_like_format(line):
  result = {}
  result['baseline'] = parse_points_page(line.get('Baseline',[]).get('points',""))
  polygon = parse_points_page(line.get('Coords',[]).get('points',""))
  if polygon:
    result['bounding_polygon_points'] = polygon
    result['bbox_xyxy'] = bbox_xyxy_from_points(result['bounding_polygon_points'])
  result['text'] = line.get('TextEquiv',{}).get('Unicode',"")
  result['confidence'] = Decimal(line.get('TextEquiv',{}).get('conf',0))
  return result

def get_page_lines(pageXMLroot):
  lines_dicts = [ element_to_dict(tl) for tl in pageXMLroot.iter(ns(pageXMLroot,"TextLine")) ]
  return [convert_to_region_like_format(pgLine) for pgLine in lines_dicts]
    
def process_task(pagesFile, pagexmlDir, regionsFile, outFile, tei_id):
  print(f"{outFile}")
  # loop over pages
  pages_meta = []
  regions = []
  with open(pagesFile, "r", encoding="utf8") as f:
    for line in f:
      pages_meta.append(json.loads(line))
  pages_meta = sorted(pages_meta, key=lambda item: item.get("n", 0))
  with open(regionsFile, "r", encoding="utf8") as f:
    for line in f:
      regions.append(json.loads(line))

  pages = []
  for i, meta in enumerate(pages_meta):
    pagexmlFile = pagexmlDir / f"{meta['uuid']}.xml"
    tree = ET.parse(pagexmlFile)
    pageXMLroot = tree.getroot()
    page = pageXMLroot.find(ns(pageXMLroot,"Page"))
    pageLines = get_page_lines(pageXMLroot)
    page_width = int(page.get("imageWidth", 0))
    page_height = int(page.get("imageHeight", 0))
    pageRegions = [item for item in regions if item.get("image",{}).get("uuid") == meta['uuid']]
    mergedRegions, notmergedLines = merge_lines_and_regions(pageLines,pageRegions)
    for region in mergedRegions:
      annotate_lines_in_region(region)
    pages.append({
      "n" : i,
      "regions" : mergedRegions,
      "page_meta" : {**meta, "width": page_width, "height": page_height},
      "outlayer_lines": notmergedLines,
    })

  sorted_regions = determine_reading_order(pages)
  ##sorted_regions = use_initial_reading_order(pages)
  tei = TEIOutput(tei_id)
  for region in sorted_regions:
    if not region.get("region_content", None):
      print(f"WARN: region without content, skipping: {region['page_meta']['uuid']} {region.get('class_name','unknown')}")
      print(dev_short(region))
    else:
      #print(f"INFO: adding region to TEI: {region}")
      print(f"INFO: adding region to TEI: BBOX:{region['all_pages_bbox_xyxy']} XSPAN:{region['all_pages_col_x_span']} PAGE:{region['page_n']} COL:{region['col_n']} STARTPAGE:{region['is_page_start']} STARTCOL:{region['is_column_start']} {region.get('class_name','unknown')}")
      tei.add_region(region)
  tei.close_current_page() # important, it calculates page hull from regions, so it has to be called after all regions are added
  tei.write(outFile)
  # 



def best_iou_match(textline, regions, min_iou=0.0):
    """
    textline_bbox: (x1, y1, x2, y2)
    yolo_bboxes: iterable of (x1, y1, x2, y2)
    min_iou: optional threshold

    returns: (best_bbox, best_iou) or (None, 0.0)
    """
    best_region = None
    best_score = 0.0

    for region in regions:
        score = 0.7 * horizontal_iou(textline.get('bbox_xyxy'), region.get('bbox_xyxy')) + 0.3 * iou_xyxy(textline.get('bbox_xyxy'), region.get('bbox_xyxy'))
        if score > best_score:
            best_score = score
            best_region = region

    if best_score < min_iou:
        return None, 0.0

    return best_region, best_score

def iou_xyxy(a, b):
    """
    a, b: (x1, y1, x2, y2)
    returns IoU float in [0, 1]
    """
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    # intersection
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih

    if inter == 0:
        return 0.0

    # areas
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)

    union = area_a + area_b - inter
    return inter / union

def vertical_iou(a, b):
    return iou_xyxy((1,a[1], 1, a[3]),(1, b[1], 1, b[3]))

def horizontal_iou(a, b):
    return iou_xyxy((a[0], 1, a[2], 1),(b[0], 1, b[2], 1))

# --------------------------

def merge_lines_and_regions(pageLines,pageRegions):
  no_match = []
  for line in pageLines:
    region, score = best_iou_match(line, pageRegions, min_iou=0.0)
    if region == None:
      no_match.append(line)
      print(f"WARN no region matched: (text conf={str(line['confidence'])}) {line['text']}")
      continue
    if not region.get("lines", None):
      region["lines"] = []
    line["intersection_score"] = score
    region["lines"].append(line)
    print(f"INFO matched line to region: (text conf={str(line['confidence'])}) {line['text']}")
      
  return pageRegions, no_match


def sliding_mean_repeat_ends(A, k):
    """
    centered sliding mean with repeated both ends:
    A = [1,2,3,4,5,6,7]
    k = 5
    result [3,3,3,4,5,5,5]
    """
    A = np.asarray(A, dtype=float)
    n = len(A)

    if k <= 0:
        raise ValueError("k must be > 0")
    if n == 0:
        return np.array([])
    if k > n:
        return np.full(n, A.mean())

    means = sliding_window_view(A, k).mean(axis=1)

    left_pad = (k - 1) // 2
    right_pad = n - len(means) - left_pad

    return np.concatenate([
        np.full(left_pad, means[0]),
        means,
        np.full(right_pad, means[-1]),
    ])





def annotate_lines_in_region(region):
  """
  parStart = bool (do it as interval???)
  parEnd = bool (do it as interval???)
  LineStart = namedtuple("LineStart", ["sentStart", "startStartNE", "sentMid", "prevHyphen"])
  LineEnd = namedtuple("LineEnd", ["sentEnd", "sentMid", "kyphen"])

  parStart = True -> sentStart = start
  parEnd = True -> sentEnd = end

  invalid values 
    - resolve with decision tree and priorities
    - position has higher priority than character recognition (Capital/interpunction/hyphen)

  """    
  window_size = 5
  parStart_indent_vs_avgHeight = 1.0
  parEnd_indent_vs_avgHeight = 2.0
  if not region.get("lines", None):
    return;
  lines = region["lines"];
  lines_boxes = np.asarray([l["bbox_xyxy"] for l in lines], dtype=float)
  windowAvgMinX = sliding_mean_repeat_ends(lines_boxes[:,0],window_size)
  windowAvgMaxX = sliding_mean_repeat_ends(lines_boxes[:,2],window_size)
  # windowAvgWidth = sliding_mean_repeat_ends(lines_boxes[:,2] - lines_boxes[:,0],window_size)
  windowAvgHeight = sliding_mean_repeat_ends(lines_boxes[:,3] - lines_boxes[:,1],window_size)
  
  rx1, ry1, rx2, ry2 = region["bbox_xyxy"]
  # paragraph indentation level
  for i,line in enumerate(lines):
    x1, y1, x2, y2 = line["bbox_xyxy"]
    line["ana"] = LineAna(
      parStart = _tri(bool(float(x1-windowAvgMinX[i]) / windowAvgHeight[i] > parStart_indent_vs_avgHeight)),
      parEnd = _tri(bool(float(windowAvgMaxX[i] - x2) / windowAvgHeight[i] > parEnd_indent_vs_avgHeight))
    )
    #print(f"start ({x1}-{windowAvgMinX[i]}) / {windowAvgHeight[i]} = {float(x1-windowAvgMinX[i]) / windowAvgHeight[i]}")
    #print(f"end ({windowAvgMaxX[i]} - {x2}) / {windowAvgHeight[i]} = {float(windowAvgMaxX[i] - x2) / windowAvgHeight[i]}")
    #print(f"LINE [width={x2-x1}] vs box [width={int(rx2-rx1)}]\n\t{line['text']}\n\t{line['ana']}\n\tAVG= {int(x1-windowAvgMinX[i])} \t {int(x2-windowAvgMaxX[i])}\n\tBOX= {int(x1-rx1)} \t {int(x2-rx2)}")
    #print(f"LINE: {'>    '*int(line['ana']['parStart'])}{line['text']}{'    <'*int(line['ana']['parEnd'])}\t{line['ana']}")
  # sentence level 
  lines_chars = [ {
      # first:
      "upper": bool(line["text"]) and line["text"][0].isupper(),
      # last:
      "punct": bool(line["text"]) and line["text"].endswith((".", "!", "?", "…")),
      "hyphen": bool(line["text"]) and line["text"].endswith(("-")),
    } for line in lines]
  for i,lch in enumerate(lines_chars):
    prev_ana = lines[i - 1]["ana"] if i > 0 else LineAna()
    prev_ch = lines_chars[i - 1] if i > 0 else {}
    next_ana = lines[i + 1]["ana"] if i + 1 < len(lines) else LineAna()
    next_ch = lines_chars[i + 1] if  i + 1 < len(lines_chars) else {}
    lines[i]["ana"] = lines[i]["ana"].annotate_line_start(lch,prev_ana, prev_ch)
    lines[i]["ana"] = lines[i]["ana"].annotate_line_end(lch, next_ana, next_ch)
    #print(f"LINE: ##{lines[i]['text']}##\n\t{lch}\n\t{lines[i]['ana']}")


##################################


def x_center(b):
  return (b[0] + b[2]) / 2

def y_top(b):
  return b[1]

def x_overlap(b1, b2):
    return max(0, min(b1[2], b2[2]) - max(b1[0], b2[0]))

def group_into_columns(items, min_overlap_ratio=0.1):
  columns = []
  for item in sorted(items, key=lambda i: i["all_pages_bbox_xyxy"][0]):
    x1, _, x2, _ = item["all_pages_bbox_xyxy"]
    w = x2 - x1

    placed = False
    for col in columns:
        cx1, cx2 = col["x_span"]
        overlap = max(0, min(x2, cx2) - max(x1, cx1))

        if overlap / w >= min_overlap_ratio:
          col["items"].append(item)
          # expand column span
          col["x_span"] = (min(cx1, x1), max(cx2, x2))
          placed = True
          break

    if not placed:
        columns.append({
          "x_span": (x1, x2),
          "items": [item],
        })
  return columns

def calculate_regions_positions_in_whole_document(pages):
  x_shift = 0
  all_regions = []
  for page in pages:
    for region in page["regions"]:
      all_regions.append({
        "page_n": page["n"],
        "all_pages_bbox_xyxy": tuple(x + y for x, y in zip((x_shift, 0, x_shift, 0),tuple(region.get("bbox_xyxy", (0,0,0,0))))),
        "is_page_start": None,
        "page_meta": page["page_meta"],
        "is_column_start": None,
        "col_n": None,
        "all_pages_col_x_span": None,
        "column_meta": None,
        "region_content": region
      })
    x_shift += page["page_meta"]["width"]
  return all_regions

def determine_reading_order(pages):
  """
  Transforms pages with regions to list of regions in right order, 
  that contains information on page and column start and proper link to facimiles

  output structure:
  [
    {
      "page_n": int,
      "is_page_start": bool,
      "page_meta": { ... page meta ... },
      "col_n": int,
      "is_column_start": bool,
      "column_meta": { ... column meta ... },
      "region_content": { ... region data ... }
    },
    ...
  ]
  """
  all_regions = calculate_regions_positions_in_whole_document(pages)

  
    #prev_region_end_pos -= (prev_page_width, 0)
    #
    #print(f"{page['n']}: {page['width']}x{page['height']} {page['page_meta']}\n")  
  columns = group_into_columns(all_regions)
  sorted_columns = sorted(columns, key=lambda c: c["x_span"][0])
  print("============ SORTED COLUMNS ============")
  print(dev_short(sorted_columns))
  sorted_regions = []
  for i, col in enumerate(sorted_columns):
    col["items"].sort(key=lambda i: i["all_pages_bbox_xyxy"][1])
    for j, item in enumerate(col["items"]):
      item["is_page_start"] = (j == 0) or (item["page_n"] != col["items"][j-1]["page_n"])
      item["is_column_start"] = (j == 0)
      item["col_n"] = i
      item["all_pages_col_x_span"] = col["x_span"]
      sorted_regions.append(item)
  print("============ SORTED REGIONS ============")
  print(dev_short(sorted_regions))
  
  return sorted_regions
  

def use_initial_reading_order(pages):
  sorted_regions = []
  all_regions = calculate_regions_positions_in_whole_document(pages)
  print("============ INITIAL REGIONS - TODO============")
  return sorted_regions
# --------------------
# TEI-part output
# --------------------

from lxml import etree
TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NSMAP = {None: TEI_NS, "xml": XML_NS}



class TEIOutput:
  tei_id: str
  TEI: etree
  texts: list = [] # nested list with pb/cb/lb
  paragraphs: list = [] # list with paragraphs
  surfaces: list = [] # list with surfaces 
  surfaces_url_to_index: dict = {}
  zones: list = [] # nested list with zones area/col/line
  
  paragraphs_i: int = 0

  texts_pb_i: int = 0
  texts_cb_i: int
  texts_lb_i: int

  zones_pb_i: int # area
  zones_cb_i: int # col
  zones_lb_i: int # line

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
  })

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
  
  def add_region(self, region):
    if region.get("is_page_start"):
      self.close_current_page()
      pb = self.start_new_page(region["page_n"], region["page_meta"], self.prev_line_end_type)
      self.el_ptr = pb
    if region.get("is_column_start"):
      self.close_current_column()
      cb = self.start_new_column(region["col_n"], self.prev_line_end_type)
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
      lb = self.start_new_line(line, self.prev_line_end_type)
      self.el_ptr = lb
      self.insert_line_text(line)



  def start_new_page(self, page_n, page_meta, prevLineEndType=LineEndCat.UNKNOWN):
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
      })

    pb_id = f"{self.tei_id}.pb{page_n}"
    surface = self.surfaces[self.surfaces_url_to_index[page_meta["url"]]]
    surface["areas_cnt"] += 1
    # create zone for area
    f_area_id = f"{surface['id']}.a{surface['areas_cnt']}"
    pb = etree.SubElement(
      self.body, 
      "{%s}pb" % TEI_NS, 
      attrib={
        "{%s}id" % XML_NS: pb_id,
        **TEIOutput.break_no(prevLineEndType),
        "n": str(page_n),
        "facs": f"#{f_area_id}"
        }
      )
    self.texts.append({
      "element": pb,
      "id": pb_id,
      "childs": [],
    })
    self.texts_cb_i = 0
    f_area = etree.SubElement(
      surface["element"], 
      "{%s}zone" % TEI_NS, 
      attrib={
        "{%s}id" % XML_NS: f_area_id,
        "start": f"#{pb_id}",
        "type": "page",
        }
      )
    self.zones_pb_i = len(self.zones)
    self.zone_pb = {
      "element": f_area,
      "id": f_area_id,
      "cols_cnt": 0,
      "childs": [],
    }
    self.zones.append(self.zone_pb)
    self.zones_cb_i = 0
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


  def start_new_column(self, col_n, prevLineEndType=LineEndCat.UNKNOWN):
    txt = self.texts[self.texts_pb_i]
    cnt= len(txt.get("childs", []))
    cb_id = f"{txt['id']}.cb{cnt+1}"
    zone = self.zones[self.zones_pb_i]
    zone["cols_cnt"] += 1
    f_col_id = f"{zone['id']}.c{zone['cols_cnt']}"
    cb = etree.SubElement(
      self.parent_el_ptr, 
      "{%s}cb" % TEI_NS, 
      attrib={
        "{%s}id" % XML_NS: cb_id,
        **TEIOutput.break_no(prevLineEndType),
        "facs": f"#{f_col_id}",
        }
      )
    txt["childs"].append({
      "element": cb,
      "id": cb_id,
      "childs": [],
    })
    self.texts_lb_i = 0
    f_col = etree.SubElement(
      zone["element"], 
      "{%s}zone" % TEI_NS, 
      attrib={
        "{%s}id" % XML_NS: f_col_id,
        "start": f"#{cb_id}",
        "type": "column",
        }
      )
    self.zones_cb_i = len(zone["childs"])
    self.zone_cb = {
      "element": f_col,
      "id": f_col_id,
      "lines_cnt": 0,
      "childs": [],
    }
    zone["childs"].append(self.zone_cb)
    self.zones_lb_i = 0
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

  def start_new_line(self, line, prevLineEndType=LineEndCat.UNKNOWN):
    txt = self.texts[self.texts_pb_i]["childs"][self.texts_cb_i]
    cnt = len(txt.get("childs", []))
    lb_id = f"{txt['id']}.lb{cnt+1}"
    zone = self.zones[self.zones_pb_i]["childs"][self.zones_cb_i]
    zone["lines_cnt"] += 1
    f_line_id = f"{zone['id']}.l{zone['lines_cnt']}"

    lb = etree.SubElement(
      self.parent_el_ptr, 
      "{%s}lb" % TEI_NS, 
      attrib={
        "{%s}id" % XML_NS: lb_id, 
        **TEIOutput.break_no(prevLineEndType),
        "facs": f"#{f_line_id}",
        }
      )
    self.texts_lb_i = len(txt["childs"])
    txt["childs"].append({
      "element": lb,
      "id": lb_id,
    })
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
    self.zones_lb_i = len(zone["childs"])
    self.zone_lb = {
      "element": f_line,
      "id": f_line_id,
      "bbox_xyxy": line.get("bbox_xyxy", (0,0,0,0)),
      "bounding_polygon_points": line.get("bounding_polygon_points", None),
    }
    zone["childs"].append(self.zone_lb)
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
        pc = etree.SubElement(self.parent_el_ptr, "{%s}pc" % TEI_NS, attrib={"force": "weak"})
        pc.text = pc_hyphen
        self.el_ptr = pc
      # print(f"INFO: line text {line.get('text','')}")
      if line.get('ana', LineAna).parEnd == Y: # paragraph end -> close paragraph
        self.parent_el_ptr = self.parent_el_ptr.getparent()
      self.prev_line_end_type = line.get('ana', LineAna).lineEnd
  
  def write(self, outFile):
    Path(outFile).parent.mkdir(parents=True, exist_ok=True)
    etree.ElementTree(self.TEI).write(
        outFile, 
        encoding="utf-8", 
        xml_declaration=True,
        pretty_print=True
      )
    print(f"INFO: output written to {outFile}")

  




# --------------------
# DEBUG
# --------------------

def print_page_regions(regions):
  for region in regions:
    print(f"========== {region['class_name']} REGION ({region['confidence']})===========")
    print(f"region bbox {region['bbox_xyxy']}")
    print(f"line cnt {len(region.get('text',[]))}")
    for line in region.get('text',[]):
      print(f"\t{line.get('text','')}")

def dev_short(obj, n=1):
    if isinstance(obj, dict):
        return {k: dev_short(v, n) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        if len(obj) > n:
            return [dev_short(v, n) for v in obj[:n]] + [f"{len(obj)-n} more..."]
        return [dev_short(v, n) for v in obj]

    return obj

# --------------------
# ARGPARSE
# --------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description=""
    )

    parser.add_argument(
        "-x", "--ocr-xml-dir",
        default="",
        type=Path,
        help="folder containing PageXML files"
    )

    parser.add_argument(
        "-r", "--regions-dir",
        required=True,
        type=Path,
        help="Path to directory with jsonl file encoded regions (one file per task)"
    )

    parser.add_argument(
        "-p", "--page-order-dir",
        required=True,
        type=Path,
        help="Path to page order folder with jsonl files (one file per task)"
    )

    parser.add_argument(
        "-t", "--tasks",
        type=Path,
        help="File with list of tasks (relative paths to files/folders), if not set, the stdin is used"
    )

    parser.add_argument(
        "-o", "--output-dir",
        required=True,
        type=Path,
        help="Output directory"
    )

    args = parser.parse_args()
    return args

def iter_lines(task_file=None):
    if task_file:
        with open(task_file, "r", encoding="utf-8") as f:
            for line in f:
                yield line.rstrip("\n")
    else:
        for line in sys.stdin:
            yield line.rstrip("\n")


# --------------------
# MAIN
# --------------------
def main():
    args = parse_args()
    for line in iter_lines(args.tasks):
        if not line:
            continue
        tei_id = line.split('/')[-1]
        print(f"INFO: component = {line}")
        print(f"INFO: id = {tei_id}")
        process_task(
          pagesFile=args.page_order_dir / f"{line}.jsonl",
          pagexmlDir=args.ocr_xml_dir / line,
          regionsFile=args.regions_dir /  f"{line}.jsonl",
          outFile=args.output_dir / f"{line}.xml",
          tei_id=tei_id
        )

if __name__ == "__main__":
    main()