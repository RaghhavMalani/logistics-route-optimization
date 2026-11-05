"""Build offline harbour context from Natural Earth 1:10m land (public domain).

Pass ne_10m_land.geojson from the pinned Natural Earth v5.1.2 release.
Requires Shapely. The existing chart stays at 1:50m outside port windows.
"""

import argparse
import json
import math
import random
from pathlib import Path

from shapely import get_parts, make_valid, prepare
from shapely.geometry import Point, Polygon, mapping, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

SRC = Path(__file__).resolve().parents[1] / "india-portwatch-terminal" / "src"

# Degrees clockwise from north. Keep the artwork on the landward side of each
# chart pin, away from the approach. JNPA faces the harbour to its northwest.
INLAND = {
    "INIXY": 315, "INMUN": 0, "INNSA": 125, "INBOM": 325, "INMRM": 100,
    "INNML": 70, "INCOK": 75, "INTUT": 270, "INMAA": 270, "INENR": 295,
    "INVTZ": 300, "INPRT": 310, "INCCU": 45,
}


def move(lon, lat, east, north):
    return lon + east / (111_320 * math.cos(math.radians(lat))), lat + north / 111_320


def disc(lon, lat, metres):
    return Polygon([
        move(lon, lat, metres * math.cos(angle), metres * math.sin(angle))
        for angle in (i * math.tau / 64 for i in range(64))
    ])


def rounded(value):
    if isinstance(value, (list, tuple)):
        return [rounded(item) for item in value]
    return round(value, 5)


def features(polygons, **properties):
    return [
        {"type": "Feature", "properties": properties,
         "geometry": {"type": "Polygon", "coordinates": rounded(mapping(poly)["coordinates"])}}
        for poly in get_parts(polygons) if poly.geom_type == "Polygon" and poly.area > 0.00000001
    ]


def collection(rows):
    return {"type": "FeatureCollection", "features": rows}


def placement(port, land):
    code, lon, lat = port["code"], port["lon"], port["lat"]
    bearing = INLAND[code]
    angle = math.radians(bearing)

    def offset(inland, lateral):
        return (inland * math.sin(angle) + lateral * math.cos(angle),
                inland * math.cos(angle) - lateral * math.sin(angle))

    # A few registry points fall in water at this coastline resolution. Shift
    # the footprint inland until its near edge has room at the closest zoom.
    clearance = next((step for step in range(0, 4501, 150)
                      if all(land.covers(Point(move(lon, lat, *offset(step + inland, lateral))))
                             for inland in (700, 1000, 1350)
                             for lateral in (-350, 0, 350))), None)
    if clearance is None:
        return None
    rng = random.Random(code)
    trees = []
    for _ in range(28):
        inland, lateral = rng.uniform(4200, 10_000), rng.uniform(-5500, 5500)
        if any(math.hypot(inland - x, lateral - z) < 1250 for x, z in trees):
            continue
        if land.covers(disc(*move(lon, lat, *offset(inland, lateral)), 600)):
            trees.append((inland, lateral))
        if len(trees) == 5:
            break
    return {"bearing": bearing, "clearance": clearance,
            "groves": [[round(east), round(north)] for east, north in (offset(*tree) for tree in trees)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("natural_earth_land", type=Path)
    args = parser.parse_args()
    asset = SRC / "assets" / "geo"
    ports = json.loads((SRC / "components" / "miniature" / "ports.generated.json").read_text(encoding="utf-8"))
    coarse = make_valid(shape(json.loads((asset / "region-land.json").read_text(encoding="utf-8"))["features"][0]["geometry"]))
    detail = [
        polygon for row in json.loads(args.natural_earth_land.read_text(encoding="utf-8"))["features"]
        for polygon in get_parts(shape(row["geometry"])) if polygon.geom_type == "Polygon"
    ]
    tree = STRtree(detail)
    windows = unary_union([disc(port["lon"], port["lat"], 24_000) for port in ports])
    shore = unary_union([make_valid(detail[index]).intersection(windows) for index in tree.query(windows)])
    prepare(shore)
    outer = unary_union([disc(port["lon"], port["lat"], 11_000) for port in ports])
    inner = unary_union([disc(port["lon"], port["lat"], 6500) for port in ports])
    corrected = coarse.difference(windows).union(shore)
    combined = collection(features(corrected))
    tint = collection(features(shore.intersection(outer.difference(inner)), band="outer")
                      + features(shore.intersection(inner), band="inner"))
    layouts = {port["code"]: placement(port, shore) for port in ports}
    layouts = {code: data for code, data in layouts.items() if data is not None}
    if layouts.keys() != INLAND.keys():
        raise ValueError(f"No shore placement for {sorted(INLAND.keys() - layouts.keys())}")
    (asset / "region-land-detail.generated.json").write_text(
        json.dumps({"land": combined, "tint": tint, "ports": layouts}, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
