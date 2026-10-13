"""Reproduce the global operational raster from public-domain Natural Earth geometry."""
import json
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1] / "india-portwatch-terminal/public/maps"
world = json.loads((ROOT / "world-countries.json").read_text(encoding="utf-8"))
width, height = 4096, 2048
image = Image.new("RGB", (width, height), "#071923")
draw = ImageDraw.Draw(image)
def point(pair):
    return ((pair[0] + 180) * width / 360, (90 - pair[1]) * height / 180)
for lon in range(-180, 181, 15):
    x = point((lon, 0))[0]
    draw.line([(x, 0), (x, height)], fill="#112a37", width=1)
for lat in range(-90, 91, 15):
    y = point((0, lat))[1]
    draw.line([(0, y), (width, y)], fill="#112a37", width=1)
for feature in world["features"]:
    geometry = feature["geometry"]
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    for polygon in polygons:
        for index, ring in enumerate(polygon):
            xy = [point(p) for p in ring]
            draw.polygon(xy, fill="#203744" if index == 0 else "#071923")
            draw.line(xy, fill="#537587", width=2)
image.save(ROOT / "nautical-world.png", optimize=True)
print("Generated global operational atlas:", image.size)
