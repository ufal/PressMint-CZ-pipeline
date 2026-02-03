#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
import json
import xml.etree.ElementTree as ET
from decimal import Decimal
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
        print(f"{ana}")
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
    result['bounding_polygon'] = polygon
    result['bbox_xyxy'] = bbox_xyxy_from_points(result['bounding_polygon'])
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
    print(f"{meta}")
    pagexmlFile = pagexmlDir / f"{meta['uuid']}.xml"
    tree = ET.parse(pagexmlFile)
    pageXMLroot = tree.getroot()
    pageLines = get_page_lines(pageXMLroot)
    pageRegions = [item for item in regions if item.get("image",{}).get("uuid") == meta['uuid']]
    mergedRegions, notmergedLines = merge_lines_and_regions(pageLines,pageRegions)
    for region in mergedRegions:
      annotate_lines_in_region(region)
    pages.append({
      "n" : i,
      "regions" : mergedRegions,
      "page_meta" : meta,
      "outlayer_lines": notmergedLines,
    })

  determine_reading_order(pages)
  tei = convert2TEI(pages, tei_id)
  Path(outFile).parent.mkdir(parents=True, exist_ok=True)
  tei.write(
        outFile, 
        encoding="utf-8", 
        xml_declaration=True,
        pretty_print=True
      )


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
  print("====== TODO: consider reimplementation with sweeping line like algorithm  ======")
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
    print(f"LINE: ##{lines[i]['text']}##\n\t{lch}\n\t{lines[i]['ana']}")



def determine_reading_order(pages):
  """
  Transforms pages with regions to list of regions in right order, 
  that contains information on page and column start and proper link to facimiles

  ??? implement as a class ???
  """
    

  print("TODO: determine_reading_order")
  

# --------------------
# TEI-part output
# --------------------

from lxml import etree
TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NSMAP = {None: TEI_NS, "xml": XML_NS}


def convert2TEI(regions, tei_id):

  TEI = etree.Element(
      "{%s}TEI" % TEI_NS,
      nsmap=NSMAP,
      attrib={
        "{%s}lang" % XML_NS: "cs",
        "{%s}id" % XML_NS: tei_id,
      }
    )
  # facsimile
  facsimile = etree.SubElement(TEI, "{%s}facsimile" % TEI_NS)
  # text/body
  text = etree.SubElement(TEI, "{%s}text" % TEI_NS)
  body = etree.SubElement(text, "{%s}body" % TEI_NS)


  return etree.ElementTree(TEI)

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