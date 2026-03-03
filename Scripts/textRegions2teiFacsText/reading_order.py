
from textRegions2teiFacsText.dev_utils import dev_short, print_page_regions


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