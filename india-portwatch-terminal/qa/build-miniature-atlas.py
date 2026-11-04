"""Restyle the retained Natural Earth atlas using the canonical map colours."""
from pathlib import Path
import re

from PIL import Image

root = Path(__file__).resolve().parents[1]
maps = root / "public/maps"
palette = (root / "src/components/miniature/palette.ts").read_text(encoding="utf-8")
colours = dict(re.findall(r'(\w+): "(#[0-9a-f]{6})"', palette))


def rgb(hex_colour):
    return tuple(bytes.fromhex(hex_colour.removeprefix("#")))


old_to_new = {
    rgb(old): rgb(colours[key])
    for old, key in (
        ("#071923", "sea"),
        ("#112a37", "graticule"),
        ("#203744", "land"),
        ("#537587", "coast"),
    )
}
with Image.open(maps / "nautical-world.png") as original:
    atlas = original.convert("RGB")
    pixels = atlas.getcolors(maxcolors=len(old_to_new))
    if pixels is None or {colour for _, colour in pixels} != old_to_new.keys():
        raise ValueError("Unexpected Natural Earth atlas colours")
    indexed = atlas.convert("P", palette=Image.Palette.ADAPTIVE, colors=len(old_to_new))
    lookup = indexed.getpalette()
    for index in range(len(old_to_new)):
        start = 3 * index
        lookup[start : start + 3] = old_to_new[tuple(lookup[start : start + 3])]
    indexed.putpalette(lookup)
    indexed.save(maps / "miniature-world.png", optimize=True)
