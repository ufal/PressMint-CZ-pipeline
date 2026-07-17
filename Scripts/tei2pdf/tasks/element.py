from tei2pdf.tasks.base import BaseTask
from tei2pdf.style_resolver import StyleResolver
from intervaltree import IntervalTree


default_config = {
  "element": ["p","pb", "cb", "lb"],
  "coordsource": ["precise", "approximate"], 
  # self: only the element itself
  # descendant: only the descendants + self
  # ancestor: only the ancestors + self
}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def element_info_to_string(elem):
    return f"{elem.tag.split('}')[1]}#{elem.get(XML_ID, '')}(facs: {elem.get('facs', '')}, children: {len(elem)})"

def has_text_between(node1, node2):
    if node1.getparent() != node2.getparent():
      if node2.getparent() == node1:
        return bool(node2.xpath("(preceding-sibling::node()[normalize-space()])"))
      elif node1.getparent() == node2:
        return bool(node2.xpath("(following-sibling::node()[normalize-space()])"))
      else:
        print(f"TODO !!! Checking text between {element_info_to_string(node1)} and {element_info_to_string(node2)}: different parents, checking siblings of {element_info_to_string(node1)}")
        return False
    for el in node1.itersiblings(preceding=False):
        print(f"Checking sibling element {element_info_to_string(el)} for text between {element_info_to_string(node1)} and {element_info_to_string(node2)}")
        if el == node2:
            break
        if (el.text and el.text.strip()) or (el.tail and el.tail.strip()):
            return True
    print(f"Checking text between {element_info_to_string(node1)} and {element_info_to_string(node2)}: no sibling elements with text found, checking tails")
    return bool(node1.tail and node1.tail.strip())

facs_coord_map = {
  "minx": lambda zone: int(zone.get("ulx")),
  "miny": lambda zone: int(zone.get("uly")),
  "maxx": lambda zone: int(zone.get("lrx")),
  "maxy": lambda zone: int(zone.get("lry")),
  "h": lambda zone: int(zone.get("lry")) - int(zone.get("uly")),
}

def get_facs_coordinate(elem, zones, coord=""):
  facs_id = elem.get("facs", "")
  print(f"FACS ID: {facs_id}")
  if  facs_id and facs_id.startswith("#") and facs_id[1:] in zones:
    zone = zones[facs_id[1:]]
    print(f"Zone for FACS ID {facs_id}: {zone.attrib}")
    return facs_coord_map[coord](zone)
  else:
    return None

def get_candidate_start(elem, zones, type="precise"):
  print(f" searching for {elem.get('facs', '<no facs>')[1:]} in zones:\n\t result={elem.get('facs', '<no facs>')[1:] in zones}")
  if elem.get("facs") and elem.get("facs", "").startswith("#") and elem.get("facs", "")[1:] in zones:
    return {
      "x": get_facs_coordinate(elem, zones, "minx"),
      "y": get_facs_coordinate(elem, zones, "miny"),
      "h": get_facs_coordinate(elem, zones, "h"),
      "type": type,
      "facs_id": elem.get("facs"," ")[1:],
      "source_elem": elem
    }
  else:
    return None

def get_candidate_end(elem, zones, type="precise"):
  print(f" searching for {elem.get('facs', '<no facs>')[1:]} in zones:\n\t result={elem.get('facs', '<no facs>')[1:] in zones}")
  if elem.get("facs") and elem.get("facs", "").startswith("#") and elem.get("facs", "")[1:] in zones:
    return {
      "x": get_facs_coordinate(elem, zones, "maxx"),
      "y": get_facs_coordinate(elem, zones, "maxy"),
      "h": get_facs_coordinate(elem, zones, "h"),
      "type": type,
      "facs_id": elem.get("facs"," ")[1:],
      "source_elem": elem
    }
  else:
    return None

def get_ancestor_adjected_start(elem, zones, type="precise"):
  if elem.tag == "{http://www.tei-c.org/ns/1.0}body":
    return None
  print(f"ANCESTOR START {element_info_to_string(elem)} with type {type}")
  # check current element
  candidate = get_candidate_start(elem, zones, type)
  if candidate:
    return candidate
  print(f"    no candidate in current element {element_info_to_string(elem)}, checking previous elements in the same level")
  # check previous elements in the same level
  prec_elem = elem.getprevious() 
  if prec_elem is not None:
    print(f"    Checking previous element {element_info_to_string(prec_elem)} for ancestor start coordinates")
    has_text_before = has_text_between(prec_elem,elem)
    type = "approximate" if has_text_before else type
    prec_has_child = bool(prec_elem.text or len(prec_elem) > 0)
    if prec_has_child or has_text_before: # use end of previous element if it has child, otherwise use start of previous element
      print(f"    Previous element {prec_elem.tag} has child or text before, checking end coordinates")
      candidate = get_descendant_adjected_end(prec_elem, zones, type)
    else:
      print(f"    Previous element {prec_elem.tag} has no child and no text before, checking start coordinates")
      candidate = get_descendant_adjected_start(prec_elem, zones, type)
    if candidate:
      return candidate
    print(f"    No candidate found in previous element {element_info_to_string(prec_elem)}, checking ancestors of previous element")
    return get_ancestor_adjected_start(prec_elem, zones, type)
  # check parent
  parent = elem.getparent()
  if parent is not None:
    has_text_before = has_text_between(parent,elem)
    type = "approximate" if has_text_before else type
    return get_ancestor_adjected_start(parent, zones, type)
  return candidate

def get_ancestor_adjected_end(elem, zones, type="precise"):
  if elem.tag == "{http://www.tei-c.org/ns/1.0}body":
    return None
  print(f"ANCESTOR END {element_info_to_string(elem)} with type {type}")
  # check current element
  candidate = get_candidate_end(elem, zones, type)
  if candidate:
    return candidate
  """
  #if there is no descendant with facs, we can check previous element
  if not get_descendant_adjected_end(elem, zones, type):
    prec_elem = elem.getprevious()
    if prec_elem is not None:
      candidate = get_descendant_adjected_end(prec_elem, zones, "approximate")
      if candidate:
        print(f"Found approximate end candidate in previous element {prec_elem.tag} for element {elem.tag}")
        return candidate
  """
  # check next elements in the same level
  next_elem = elem.getnext() 
  if next_elem is not None:
    has_text_after = has_text_between(elem, next_elem)
    type = "approximate" if has_text_after else type
    candidate = get_descendant_adjected_start(next_elem, zones, type)
    if candidate:
      return candidate
    return get_descendant_adjected_start(next_elem, zones, type)
  # check parent
  parent = elem.getparent()
  if parent is not None:
    has_text_after = has_text_between(elem, parent)
    type = "approximate" if has_text_after else type
    return get_ancestor_adjected_end(parent, zones, type)
  return candidate


def get_descendant_adjected_start(elem, zones, type="precise"):
    print(f"DESCENDANT START {element_info_to_string(elem)} with type {type}")
    candidate = get_candidate_start(elem, zones, type)
    if candidate:
      return candidate
    for child in elem:
      has_text_before = has_text_between(elem, child)
      print(f"Checking child element {element_info_to_string(child)} for descendant start coordinates, has text before: {has_text_before}")
      child_type = "approximate" if has_text_before else type
      candidate = get_descendant_adjected_start(child, zones, child_type)
      if candidate:
        return candidate
    return None

def get_descendant_adjected_end(elem, zones, type="precise"):
    print(f"DESCENDANT END {element_info_to_string(elem)} with type {type}")
    candidate = get_candidate_end(elem, zones, type)
    if candidate:
      print(f"Found candidate end coordinates in element {element_info_to_string(elem)} with type {type}")
      return candidate
    for child in reversed(elem):
      has_text_after = has_text_between(elem, child)
      child_type = type
      if len(child) > 0:
         child_type = "approximate" if has_text_after else type
      candidate = get_descendant_adjected_end(child, zones, child_type)
      if candidate:
        return candidate
    return None

def get_adjected(elem, zones, which, where="start", type="precise"):
  """
    which: ancestor, descendant, self
    where: start, end
    type: precise, approximate
  """
  if which == "ancestor":
    if where == "start":
      return get_ancestor_adjected_start(elem, zones, type)
    else:
      return get_ancestor_adjected_end(elem, zones, type)
  elif which == "self":
    if where == "start":
      return get_candidate_start(elem, zones, type)
    else:
      return get_candidate_end(elem, zones, type)
  elif which == "descendant":
    if where == "start":
      return get_descendant_adjected_start(elem, zones, type)
    else:
      return get_descendant_adjected_end(elem, zones, type)


class ElementTask(BaseTask):
    def __init__(self, config):
        super().__init__({**default_config, **config})
        self.used_positions = dict()
        for elem in self.config["element"]: 
          filter = set()
          filter.add(elem)
          filter.add("element")
          print (f"Adding filter for element '{elem}': {filter}")
          self.filter.append(filter)

    def run_at_position(self, canvas, surface, position, shared_context):
        xpos, ypos = position
        w=shared_context["page_width"]
        h=shared_context["page_height"]
        # facs and no child inside -> top-left
        # facs and child -> top-left + bottom-right
        # no facs and child with facs -> top-left of first child with facs + bottom-right of last child
        # no facs and no child -> center of parent bbox
        zones = {
          zone.get(XML_ID): zone
          for zone in surface.xpath(".//tei:zone", namespaces=shared_context["ns"])
        }
        seen_on_surface = False
        for elem in shared_context["root"].findall(".//tei:text//tei:*", namespaces=shared_context["ns"]):
          features = {"element", elem.tag.split("}")[1]}
          if not self.match_features(features, shared_context):
            # print (f"DEBUG: Skipping element '{elem.tag}' (features: {features})")
            continue
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
          ## TODO IMPROVE CHECKING WHETHER ELEMENT IS ON SURFACE
          # self with facs
          elem_s = elem.xpath("self::*[@facs]", namespaces=shared_context["ns"]) 
          # preceding element with facs
          elem_p = elem.xpath("preceding::*[@facs]", namespaces=shared_context["ns"])
          # following element with facs
          elem_f = elem.xpath("following::*[@facs]", namespaces=shared_context["ns"])
          # first descendant with facs
          elem_d1 = elem.xpath("descendant::*[@facs]", namespaces=shared_context["ns"])
          # last descendant with facs
          elem_d2 = elem.xpath("descendant::*[@facs][last()]", namespaces=shared_context["ns"])



          start, end = self.get_position(elem, zones, shared_context)
          if (start or end) and not seen_on_surface:
            print(f"FIRST ELEMENT ON SURFACE:\nElement {element_info_to_string(elem)} has coordinates: start={start}, end={end}")
            seen_on_surface = True
          print(f"ELEMENT {element_info_to_string(elem)}: \n\tSTART: {start} \n\tEND: {end}")
          for pos,shift in [(start,1), (end,-1)]:
            if pos and pos["type"] in self.config["coordsource"]:
              shared_context["styles"].apply(canvas, features)
              print(f"Element {element_info_to_string(elem)} at ({pos['x']}, {pos['y']})")
              while self.used_position(pos):
                pos["x"] += shift * 1
              print(f"Drawing element {element_info_to_string(elem)} at ({pos['x']}, {pos['y']}) with height {shift*pos['h']} and shift {shift}")
              canvas.rect(*self.transform_position((pos['x'], pos['y']), xpos, ypos, w, h), 1, -1*shift * pos['h'], stroke=1, fill=0)
          if start and end:
            shared_context["styles"].apply(canvas, features)
            self.draw_path(canvas, 
                           [(start['x'], start['y']+start['h']/2), (end['x'], end['y']-end['h']/2)], xpos, ypos, w, h)
          
    def used_position(self, pos):
        key = (pos["x"], pos["y"], pos["h"])
        if pos["x"] in self.used_positions:
          if self.used_positions[pos["x"]].overlaps(pos["y"], pos["y"] + pos["h"]):
            return True
        else:
          self.used_positions[pos["x"]] = IntervalTree()
        self.used_positions[pos["x"]].addi(pos["y"], pos["y"] + pos["h"])
        return False

    def get_position(self, elem, zones, shared_context):
        has_child = bool(elem.text) or len(elem) > 0
        facs_id = elem.get("facs", "")
        print("======================================================================")
        print(f"Processing element {element_info_to_string(elem)} with FACS ID {facs_id} and child: {has_child}")
        if facs_id.startswith("#") and facs_id[1:] in zones:
            # facs and no child inside -> top-left
            # facs and child -> top-left + bottom-right
            print(f"Element {elem.tag} has FACS ID {facs_id} and child: {has_child}")
            zone = zones[facs_id[1:]]
            start = {
              "x": get_facs_coordinate(elem, zones, "minx"), 
              "y": get_facs_coordinate(elem, zones, "miny"), 
              "h": get_facs_coordinate(elem, zones, "h"), 
              "type": "precise", 
              "facs_id": facs_id[1:], 
              "source_elem": elem
              }
            end = None
            if has_child:
                end = {
                  "x": get_facs_coordinate(elem, zones, "maxx"), 
                  "y": get_facs_coordinate(elem, zones, "maxy"), 
                  "h": get_facs_coordinate(elem, zones, "h"), 
                  "type": "precise", 
                  "facs_id": facs_id[1:], 
                  "source_elem": elem
                  }
            return (start, end)
        else:
          coordinates = {}
          for which in ["descendant", "ancestor"]:
            for where in ["start", "end"]:
              print (f"======\nChecking {which} {where} coordinates for element {element_info_to_string(elem)}")  
              adjected = get_adjected(elem, zones, which, where)
              print (f"######\nAdjected {which} {where} coordinates for element {element_info_to_string(elem)}: {adjected}")
              if (adjected 
                and adjected["facs_id"] in zones
                and (
                  ( f"{where}" in coordinates and coordinates.get(f"{where}", {}).get("type") != "precise")
                  or f"{where}" not in coordinates
                )):
                coordinates[f"{where}"] = adjected
                print (f"   == using in {adjected['type']} result {'(can be overwritten)' if adjected['type'] != 'precise' else ''}")
          print (f"Adjected coordinates for element {element_info_to_string(elem)}: {coordinates}\n======")
          
          return coordinates.get("start", None), coordinates.get("end", None)
    



