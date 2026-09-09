"""Build the terminal's bundled basemap from Natural Earth.

The operations map does not call a tile service. A control-room console has to
draw the coastline on a closed network, and a hosted basemap would also put an
uncontrolled third party between the operator and the chart. So the coastline
and the national boundaries ship in the repository as two clipped GeoJSON
files, and this script is how they are regenerated.

Source (public domain, Natural Earth 1:50m):
  ne_50m_land.geojson
  ne_50m_admin_0_boundary_lines_land.geojson
  https://github.com/nvkelso/natural-earth-vector/tree/master/geojson

Usage:
  curl -sSLO https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_land.geojson
  curl -sSLO https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_boundary_lines_land.geojson
  python scripts/build_basemap.py --land ne_50m_land.geojson       --borders ne_50m_admin_0_boundary_lines_land.geojson

Geometry is clipped (Sutherland-Hodgman) to the Indian Ocean theatre -- wide
enough to hold Suez, Hormuz, Bab-el-Mandeb and Malacca alongside the Indian
coast -- and rounded, which takes 2.4 MB of source down to ~190 KB.
"""

import argparse
import json
from pathlib import Path

BBOX = (24.0, -14.0, 114.0, 44.0)  # minlon, minlat, maxlon, maxlat


def _inside(p, edge):
    x, y = p
    minx, miny, maxx, maxy = BBOX
    return {0: x >= minx, 1: y >= miny, 2: x <= maxx, 3: y <= maxy}[edge]


def _intersect(a, b, edge):
    minx, miny, maxx, maxy = BBOX
    (x1, y1), (x2, y2) = a, b
    if edge in (0, 2):
        xe = minx if edge == 0 else maxx
        t = (xe - x1) / (x2 - x1) if x2 != x1 else 0.0
        return [xe, y1 + t * (y2 - y1)]
    ye = miny if edge == 1 else maxy
    t = (ye - y1) / (y2 - y1) if y2 != y1 else 0.0
    return [x1 + t * (x2 - x1), ye]


def clip_ring(ring):
    out = ring
    for edge in range(4):
        if not out:
            return []
        inp, out = out, []
        prev = inp[-1]
        for cur in inp:
            if _inside(cur, edge):
                if not _inside(prev, edge):
                    out.append(_intersect(prev, cur, edge))
                out.append(list(cur))
            elif _inside(prev, edge):
                out.append(_intersect(prev, cur, edge))
            prev = cur
    return out


def clip_line(line):
    """Split a linestring on the box, returning the segments that stay inside."""
    minx, miny, maxx, maxy = BBOX
    def within(p):
        return minx <= p[0] <= maxx and miny <= p[1] <= maxy
    parts, cur = [], []
    for p in line:
        if within(p):
            cur.append(list(p))
        elif cur:
            parts.append(cur)
            cur = []
    if cur:
        parts.append(cur)
    return [p for p in parts if len(p) > 1]


def rnd(coords, nd=2):
    if isinstance(coords[0], (int, float)):
        return [round(float(coords[0]), nd), round(float(coords[1]), nd)]
    return [rnd(c, nd) for c in coords]


def dedupe(ring):
    out = []
    for p in ring:
        if not out or p != out[-1]:
            out.append(p)
    return out


def polygons(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return geom["coordinates"]
    return []


def lines(geom):
    if geom["type"] == "LineString":
        return [geom["coordinates"]]
    if geom["type"] == "MultiLineString":
        return geom["coordinates"]
    return []


def build_land(path, nd):
    src = json.load(open(path, encoding="utf-8"))
    out = []
    for feat in src["features"]:
        for poly in polygons(feat["geometry"]):
            rings = []
            for ring in poly:
                clipped = clip_ring(ring)
                if len(clipped) < 4:
                    continue
                simple = dedupe(rnd(clipped, nd))
                if len(simple) >= 4:
                    if simple[0] != simple[-1]:
                        simple.append(simple[0])
                    rings.append(simple)
            if rings:
                out.append(rings)
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": {
            "type": "MultiPolygon", "coordinates": out}}]}


def build_lines(path, nd):
    src = json.load(open(path, encoding="utf-8"))
    out = []
    for feat in src["features"]:
        for line in lines(feat["geometry"]):
            for part in clip_line(line):
                simple = dedupe(rnd(part, nd))
                if len(simple) > 1:
                    out.append(simple)
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": {
            "type": "MultiLineString", "coordinates": out}}]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--land", default="ne_50m_land.geojson")
    parser.add_argument("--borders",
                        default="ne_50m_admin_0_boundary_lines_land.geojson")
    parser.add_argument("--out", default="india-portwatch-terminal/src/assets/geo")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    land = build_land(args.land, 3)
    borders = build_lines(args.borders, 2)
    for name, payload in (("region-land.json", land),
                          ("region-borders.json", borders)):
        target = out_dir / name
        target.write_text(json.dumps(payload, separators=(",", ":")),
                          encoding="utf-8")
        print(f"{target} {target.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
