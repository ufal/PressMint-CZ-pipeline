import json
import xml.etree.ElementTree as ET
from decimal import Decimal
from scipy.spatial import ConvexHull
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from textRegions2teiFacsText.line_ana import LineAna, LineEndCat, Y, tri
from textRegions2teiFacsText.reading_order import determine_reading_order
from textRegions2teiFacsText.tei_output import TEIOutput
from textRegions2teiFacsText.separators import detect_separators


def get_ns(el):
    return el.tag.split("}")[0].strip("{")
def get_name(el):
    return el.tag.split("}", 1)[1]

def ns(r,t):
  NS=get_ns(r)
  return f"{{{NS}}}{t}"


# geometry utils
def parse_points_page(points_str):
    """PAGE: 'x,y x,y ...'"""
    return [tuple(map(int, p.split(","))) for p in points_str.split()]

def bbox_xyxy_from_points(points):
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return [ min(xs), min(ys), max(xs), max(ys) ]
# iou utils

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


# line annotation utils


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
      parStart = tri(bool(float(x1-windowAvgMinX[i]) / windowAvgHeight[i] > parStart_indent_vs_avgHeight)),
      parEnd = tri(bool(float(windowAvgMaxX[i] - x2) / windowAvgHeight[i] > parEnd_indent_vs_avgHeight))
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



# region utils

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

def convert_to_region_like_format(line):
  result = {}
  result['baseline'] = parse_points_page(line.get('Baseline', {}).get('points',""))
  polygon = parse_points_page(line.get('Coords', {}).get('points',""))
  if polygon:
    result['bounding_polygon_points'] = polygon
    result['bbox_xyxy'] = bbox_xyxy_from_points(result['bounding_polygon_points'])
  result['text'] = line.get('TextEquiv', {}).get('Unicode',"")
  result['confidence'] = Decimal(line.get('TextEquiv',{}).get('conf',0))
  return result

def get_page_lines(pageXMLroot):
  lines_dicts = [ element_to_dict(tl) for tl in pageXMLroot.iter(ns(pageXMLroot,"TextLine")) ]
  return [convert_to_region_like_format(pgLine) for pgLine in lines_dicts]

def get_page_text_regions(pageXMLroot):
  text_region_dicts = [ element_to_dict(tr) for tr in pageXMLroot.iter(ns(pageXMLroot,"TextRegion")) ]
  return [convert_to_region_like_format(pgRegion) for pgRegion in text_region_dicts]

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
    textRegions = get_page_text_regions(pageXMLroot)
    for region in mergedRegions:
      annotate_lines_in_region(region)
    pages.append({
      "n" : i,
      "regions" : mergedRegions,
      "page_meta" : {**meta, "width": page_width, "height": page_height},
      "outlayer_lines": notmergedLines,
      "text_regions": textRegions, # these are the text regions from pagexml, they are added as zones to TEI
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
    tei.add_zone(region['region_content'], "imageRegion", region['page_meta']['url'])
  for page in pages:
    for line in page["outlayer_lines"]:
      print(f"WARN: line without region, adding as outlayer: (text conf={str(line['confidence'])}) {line['text']}")
      tei.add_zone(line, "outlayerLine", page["page_meta"]["url"])
    for text_region in page["text_regions"]:
      tei.add_zone(text_region, "textRegion", page["page_meta"]["url"])
    for separator in detect_separators([region['bounding_polygon_points'] for region in page["text_regions"]]):
      tei.add_path(separator.get("path", []), separator.get("orientation", "unknown"),separator.get("thickness", 1), page["page_meta"]["url"])
  tei.close_current_page() # important, it calculates page hull from regions, so it has to be called after all regions are added
  tei.write(outFile)
