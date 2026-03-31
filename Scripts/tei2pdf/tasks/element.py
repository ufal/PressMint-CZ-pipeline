from tei2pdf.tasks.base import BaseTask
from tei2pdf.style_resolver import StyleResolver

default_config = {
  "element": ["p","pb", "cb", "lb"],
  "coordsource": ["precise", "approximate"], 
  # self: only the element itself
  # descendant: only the descendants + self
  # ancestor: only the ancestors + self
}

def has_text_between(node1, node2):
    for el in node1.itersiblings(preceding=False):
        if el == node2:
            break
        if (el.text and el.text.strip()) or (el.tail and el.tail.strip()):
            return True
    return bool(node1.tail and node1.tail.strip())

facs_coord_map = {
  "minx": lambda zone: int(zone.get("ulx")),
  "miny": lambda zone: int(zone.get("uly")),
  "maxx": lambda zone: int(zone.get("lrx")),
  "maxy": lambda zone: int(zone.get("lry")),
  "h": lambda zone: int(zone.get("lry")) - int(zone.get("uly")),
}

def get_facs_coordinate(elem, facs, coord=""):
  facs_id = elem.get("facs", "")
  if facs_id.startswith("#") and facs_id[1:] in facs:
    zone = facs[facs_id[1:]]
    return facs_coord_map[coord](zone)
  else:
    return None

def get_ancestor_adjected_start(elem, facs, type="precise"):
  prec_elem = elem.previous()
  if prec_elem is not None:
    prec_has_child = bool(prec_elem.text or len(prec_elem) > 0)
    has_text_before = has_text_between(elem, prec_elem)
    if has_text_before:
      type = "approximate"
    if prec_elem.get("facs", "").startswith("#"):
      if prec_has_child: # use end of previous element if it has child, otherwise use start of previous element
        return {
          "x": get_facs_coordinate(prec_elem, facs, "maxx"), 
          "y": get_facs_coordinate(prec_elem, facs, "maxy"), 
          "h": get_facs_coordinate(prec_elem, facs, "h"), 
          "type": type, 
          "facs_id": prec_elem.get("facs"), 
          "source_elem": prec_elem
          }
      else:
        return {
          "x": get_facs_coordinate(prec_elem, facs, "minx"), 
          "y": get_facs_coordinate(prec_elem, facs, "miny"), 
          "h": get_facs_coordinate(prec_elem, facs, "h"), 
          "type": type, 
          "facs_id": prec_elem.get("facs"), 
          "source_elem": prec_elem
         }
    candidate = get_descendant_adjected_end(prec_elem, type=type)
    if candidate:
      return candidate
    candidate = get_ancestor_adjected_start(prec_elem, type=type)
    if candidate:
      return candidate
    else:
      return None
  else:
    parent = elem.getparent()
    has_text_before = has_text_between(elem, parent)
    if has_text_before:
      type = "approximate"
    if parent.get("facs", "").startswith("#"):
      return {
        "x": get_facs_coordinate(parent, facs, "minx"),
        "y": get_facs_coordinate(parent, facs, "miny"),
        "h": get_facs_coordinate(parent, facs, "h"),
        "type": type,
        "facs_id": parent.get("facs"),
        "source_elem": parent
      }
    else:
      return get_ancestor_adjected_start(parent, type=type)


  has_text_before = has_text_between(elem, parent)
  if has_text_before:
    type = "approximate"

def get_descendant_adjected_start(elem, facs, type="precise"):
    pass


def get_adjected(elem, facs, which, where="start", type="precise"):
  """
    which: ancestor, descendant, self
    where: start, end
    type: precise, approximate
  """
  if which == "ancestor":
    if where == "start":
      pass
    else:
      pass
  elif which == "descendant":
    if where == "start":
      pass
    else:
      pass


class ElementTask(BaseTask):
    def __init__(self, config):
        super().__init__({**default_config, **config})

    def run_at_position(self, canvas, surface, position, shared_context):
        x, y = position
        # facs and no child inside -> top-left
        # facs and child -> top-left + bottom-right
        # no facs and child with facs -> top-left of first child with facs + bottom-right of last child
        # no facs and no child -> center of parent bbox
        zones = surface.xpath(".//tei:zone", namespaces=shared_context["ns"])
        facs_ids = {
          el.get("facs")[1:]: el
          for el in shared_context["root"].xpath(".//tei:*[@facs]", namespaces=shared_context["ns"])
          if el.get("facs", "").startswith("#")
        }
        for elem in shared_context["root"].findall(".//tei:text//tei:*", namespaces=shared_context["ns"]):
          # filter elements matching coordsource
          if elem.tag.split("}")[1] not in self.config["element"]:
            continue
          # filter elements that is on the page (sources facs is in facs_ids)

          #start_x, start_y, start_h, start_pos_type, end_x, end_y, end_h, end_pos_type = 
          """
            {
              "x": 100,
              "y": 100,
              "h": 0,
              "type": "precise" # precise, approximate
              "facs_id": "facs1",
              "source_elem": <element>
            }
          """
          start, end = self.get_position(elem, zones, facs_ids, shared_context)
          if start["type"] in self.config["coordsource"]:
            style = StyleResolver.resolve_style(elem, shared_context["ns"])
            font_size = style.get("font-size", 12)
            canvas.setFont("Helvetica", font_size)
            canvas.setFillColorRGB(0, 0, 0)
            canvas.drawString(x + start["x"], y + start["y"], elem.text or "")


    def get_position(self, elem, zones, facs_ids, shared_context):
        has_child = bool(elem.text) or len(elem) > 0
        facs_id = elem.get("facs", "")
        
        if facs_id.startswith("#") and facs_id[1:] in facs_ids:
            # facs and no child inside -> top-left
            # facs and child -> top-left + bottom-right
            zone = facs_ids[facs_id[1:]]
            start = {
              "x": get_facs_coordinate(elem, facs_ids, "minx"), 
              "y": get_facs_coordinate(elem, facs_ids, "miny"), 
              "h": get_facs_coordinate(elem, facs_ids, "h"), 
              "type": "precise", 
              "facs_id": facs_id, 
              "source_elem": elem
              }
            end = None
            if has_child:
                end = {
                  "x": get_facs_coordinate(elem, facs_ids, "maxx"), 
                  "y": get_facs_coordinate(elem, facs_ids, "maxy"), 
                  "h": get_facs_coordinate(elem, facs_ids, "h"), 
                  "type": "precise", 
                  "facs_id": facs_id, 
                  "source_elem": elem
                  }
            return start, end
        coordinates = {}
        for which in ["ancestor", "descendant"]:
          for where in ["start", "end"]:
            adjected = get_adjected(elem, facs_ids, which, where)
            if (adjected 
              and adjected["facs_id"] in facs_ids
              and f"{which}_{where}" in adjected 
              and adjected["type"] != "approximate"):
              coordinates[f"{which}_{where}"] = adjected
        



