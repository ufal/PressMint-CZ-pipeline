#!/usr/bin/env python3
"""Detect long horizontal rules (separator lines) in page images.

Rules may span the whole page or only a part of it (e.g. two columns above a
feuilleton).  Morphological opening with a long horizontal kernel keeps only
long dark horizontal runs; short gaps (broken print, slight skew) are bridged.

Output: one JSON per page  {image, width, height, rules:[{bbox:[x0,y0,x1,y1], length}]}
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def detect(path, min_frac=0.12, scale=0.5):
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    H, W = img.shape
    small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    h, w = small.shape
    bw = cv2.adaptiveThreshold(small, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)
    # keep horizontal runs >= 4 % of width (text glyphs/words are shorter)
    k = max(20, int(0.04 * w))
    runs = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (k, 1)))
    # bridge small gaps and slight skew between segments of one rule
    runs = cv2.morphologyEx(runs, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (int(0.02 * w), 5)))
    n, _, stats, _ = cv2.connectedComponentsWithStats(runs, 8)
    rules = []
    for i in range(1, n):
        x, y, rw, rh = stats[i, :4]
        if rw < min_frac * w or rh > 0.012 * h:      # too short / too thick (block of text)
            continue
        # a rule is mostly ink along its length (filters long underlined words, borders of photos)
        fill = stats[i, cv2.CC_STAT_AREA] / float(rw * rh)
        if fill < 0.3:
            continue
        s = 1 / scale
        rules.append({"bbox": [int(x * s), int(y * s), int((x + rw) * s), int((y + rh) * s)],
                      "length": int(rw * s)})
    # merge rules that are vertically adjacent (double / triple lines) into one
    rules.sort(key=lambda r: (r["bbox"][1], r["bbox"][0]))
    merged = []
    for r in rules:
        for m in merged:
            a, b = m["bbox"], r["bbox"]
            xo = min(a[2], b[2]) - max(a[0], b[0])
            if xo > 0.7 * min(a[2] - a[0], b[2] - b[0]) and b[1] - a[3] < 0.006 * H:
                m["bbox"] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                m["length"] = m["bbox"][2] - m["bbox"][0]
                break
        else:
            merged.append(r)
    return W, H, merged


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-i", "--images", required=True, type=Path)
    ap.add_argument("-o", "--output", required=True, type=Path)
    args = ap.parse_args()
    images = sorted(args.images.glob("*.jpg"))
    if not images:
        # without images the layout analysis would silently run without rules;
        # fail before creating the output dir (make would skip an existing one next time)
        raise SystemExit(f"ERROR: no page images (*.jpg) in {args.images}")
    args.output.mkdir(parents=True, exist_ok=True)
    for img in images:
        W, H, rules = detect(img)
        (args.output / f"{img.stem}.json").write_text(json.dumps(
            {"image": img.name, "width": W, "height": H, "rules": rules}, indent=1))
        print(f"{img.name}: {len(rules)} rules")


if __name__ == "__main__":
    main()
