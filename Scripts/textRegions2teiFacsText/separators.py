from shapely.geometry import Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

def bbox(poly):
    return poly.bounds
  

def overlap_1d(a1, a2, b1, b2):
    return max(0, min(a2, b2) - max(a1, b1))


def crop_polygon_y(poly, center_y, dist):
    clip = box(-1e9, center_y - dist, 1e9, center_y + dist)
    return poly.intersection(clip)

def crop_polygon_x(poly, center_x, dist):
    clip = box(center_x - dist, -1e9, center_x + dist, 1e9)
    return poly.intersection(clip)


def detect_separators(coords,
                      min_xgap=-10,
                      max_xgap=10,
                      min_ygap=5,
                      max_ygap=120,
                      min_overlap=50,
                      merge_tol=50):
    polygons = [Polygon(p) for p in coords]
    tree = STRtree(polygons)

    vertical = []
    horizontal = []

    for poly in polygons:

        minx1, miny1, maxx1, maxy1 = bbox(poly)
        candidate_ids = tree.query(poly.buffer(max(max_xgap, max_ygap)))

        for idx in candidate_ids:
            other = polygons[idx]

            if poly == other:
                continue

            minx2, miny2, maxx2, maxy2 = bbox(other)

            # ---- vertical divider ----
            gap = minx2 - maxx1
            if min_xgap <= gap <= max_xgap:

                ov = overlap_1d(miny1, maxy1, miny2, maxy2)

                if ov > min_overlap:

                    center_x = (maxx1 + minx2) / 2
                    _, minyc1, _, maxyc1 = bbox(crop_polygon_x(poly, center_x, 2*max_xgap))
                    _, minyc2, _, maxyc2 = bbox(crop_polygon_x(other, center_x, 2*max_xgap))

                    y1 = min(minyc1, minyc2)
                    y2 = max(maxyc1, maxyc2)

                    vertical.append({
                        "orientation": "vertical",
                        "path": [(center_x, y1), (center_x, y2)],
                        "thickness": gap
                    })

            # ---- horizontal divider ----
            gap = miny2 - maxy1
            if min_ygap <= gap <= max_ygap:

                ov = overlap_1d(minx1, maxx1, minx2, maxx2)

                if ov > min_overlap:

                    center_y = (maxy1 + miny2) / 2
                    minxc1,_,maxxc1,_ = bbox(crop_polygon_y(poly, center_y, 2*max_ygap))
                    minxc2,_,maxxc2,_ = bbox(crop_polygon_y(other, center_y, 2*max_ygap))

                    x1 = min(minxc1, minxc2)
                    x2 = max(maxxc1, maxxc2)

                    horizontal.append({
                        "orientation": "horizontal",
                        "path": [(x1, center_y), (x2, center_y)],
                        "thickness": gap
                    })

    vertical = merge_segments(vertical, "vertical", merge_tol)
    horizontal = merge_segments(horizontal, "horizontal", merge_tol)

    return vertical + horizontal

def merge_segments(segments, orientation, align_tol=15, gap_tol=40, thick_tol=0.4):
    """
    Merge separator segments that:
      - lie on the same center line
      - have similar thickness
      - are close or touching

    Parameters
    ----------
    segments : list
        separator dicts
    orientation : str
        "vertical" or "horizontal"
    align_tol : int
        tolerance for line alignment
    gap_tol : int
        max gap between segments to merge
    thick_tol : float
        allowed relative thickness difference (0.4 = 40%)
    """

    if not segments:
        return []

    # sort segments along the main direction
    if orientation == "vertical":
        segments.sort(key=lambda s: (s["path"][0][0], s["path"][0][1]))
    else:
        segments.sort(key=lambda s: (s["path"][0][1], s["path"][0][0]))

    merged = []
    current = segments[0].copy()

    for seg in segments[1:]:

        if orientation == "vertical":

            x_curr = current["path"][0][0]
            x_new = seg["path"][0][0]

            # check alignment
            aligned = abs(x_curr - x_new) < align_tol

            # check vertical gap
            curr_end = current["path"][1][1]
            new_start = seg["path"][0][1]
            close = abs(new_start - curr_end) < gap_tol

        else:

            y_curr = current["path"][0][1]
            y_new = seg["path"][0][1]

            aligned = abs(y_curr - y_new) < align_tol

            curr_end = current["path"][1][0]
            new_start = seg["path"][0][0]
            close = abs(new_start - curr_end) < gap_tol

        # thickness similarity
        t1 = current["thickness"]
        t2 = seg["thickness"]
        den = max(t1, t2, 1e-6)
        similar_thickness = abs(t1 - t2) / den < thick_tol

        if aligned and close and similar_thickness:

            # extend segment
            if orientation == "vertical":
                current["path"][1] = (
                    (current["path"][1][0] + seg["path"][1][0]) / 2,
                    seg["path"][1][1],
                )
            else:
                current["path"][1] = (
                    seg["path"][1][0],
                    (current["path"][1][1] + seg["path"][1][1]) / 2,
                )

            # update thickness (running average)
            current["thickness"] = (t1 + t2) / 2

        else:
            merged.append(current)
            current = seg.copy()

    merged.append(current)

    return merged