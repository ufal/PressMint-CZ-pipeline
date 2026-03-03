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