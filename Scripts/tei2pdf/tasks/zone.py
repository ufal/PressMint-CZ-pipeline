from tei2pdf.tasks.base import BaseTask
from tei2pdf.style_resolver import StyleResolver

default_config = {
  "coordtype": "polygon/bbox",
  "zone_type": "all",
}

class ZoneTask(BaseTask):
    def __init__(self, config):
        super().__init__({**default_config, **config})
        self.filter.add("zone")
        if "coordtype" in config:
            self.filter.add(config['coordtype'])
        if "zone_type" in config:
            self.filter.add(config['zone_type'])
        if "linked" in config:
            if config["linked"]:
                self.filter.add("linked")
            else:
                self.filter.add("notlinked")
        else:
            self.filter.add("linked+notlinked")

    def run_at_position(self, canvas, surface, position, shared_context):
        x, y = position
        print(f"[Zone] pos={position}")
        
        zones = surface.xpath(".//tei:zone", namespaces=shared_context["ns"])
        facs_ids = {
          el.get("facs")[1:]: el
          for el in shared_context["root"].xpath(".//tei:*[@facs]", namespaces=shared_context["ns"])
          if el.get("facs", "").startswith("#")
        }
        for zone in zones:
          zid = zone.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
          is_points = bool(zone.get("points"))
          is_box = bool(zone.get("ulx") and zone.get("lrx") and zone.get("uly") and zone.get("lry"))
          is_linked = zid in facs_ids
          zone_features = {"zone"}
          if is_points:
            zone_features.add("polygon")
            zone_features.add("polygon/bbox")
          if is_box:
            zone_features.add("bbox")
          if is_points and is_box:
            zone_features.add("polygon+bbox")
          if not is_points and not is_box:
            print(f"Warning: zone '{zid}' has neither points nor box coordinates, skipping.")
            continue
          if is_linked:
            zone_features.add("linked")
          else:
            zone_features.add("notlinked")
          zone_features.add("linked+notlinked")
          if zone.attrib.get("type"):
            zone_features.add(zone.attrib.get("type"))
            zone_features.add("all")

          if not self.match_features(zone_features, shared_context):
            # task doesn't match the features of this zone, skip it
            ##print(f"DEBUG: Skipping zone '{zid}' (features: {zone_features})")
            continue
          shared_context["styles"].apply(canvas, zone_features)

          points = [] 
          if is_points and self.config.get("coordtype", "") in ("polygon", "polygon/bbox", "polygon+bbox"):
            points.append(self.parse_points(zone.get("points")))
          if is_box and (self.config.get("coordtype", "") in ("bbox", "polygon+bbox") or not is_points):
            ulx = float(zone.get("ulx"))
            uly = float(zone.get("uly"))
            lrx = float(zone.get("lrx"))
            lry = float(zone.get("lry"))
            points.append([(ulx, uly), (lrx, uly), (lrx, lry), (ulx, lry)])
          print(f"points: {points}")
          for pts in points:
            print(f"INFO  - zone '{zid}' features={zone_features} points={pts} filter={self.filter}")
            self.draw_path(canvas, pts, x=x, y=y, w=shared_context["page_width"], h=shared_context["page_height"], closed=True)
          
