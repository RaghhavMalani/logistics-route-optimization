# Global scene basemaps

`world-countries.json`: Natural Earth 1:110m admin-0 countries, from
https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_countries.geojson
retrieved October 9, 2026. Public domain:
https://www.naturalearthdata.com/about/terms-of-use/

`nautical-world.png` is a global equirectangular operational rendering of that
geometry, reproduced by `scripts/build_nautical_atlas.py`. It is general geographic
context, not a navigational chart or surveyed terminal. The SVG fallback uses the
same geometry with interactive pan, zoom and selection.

The optional browser-direct imagery view uses NASA GIBS Blue Marble shaded relief
and bathymetry, a static geographic composite, not current satellite observations.
No API key, paid account, bulk download or terrain source is connected.
Acknowledgment: We acknowledge the use of imagery provided by services from NASA's
Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and
Information System (ESDIS).
https://nasa-gibs.github.io/gibs-api-docs/
