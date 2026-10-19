# Chennai / INMAA feasibility

Chennai remains a feasible second port, not an implemented second twin. Its
authority publishes a [master plan](https://www.chennaiport.gov.in/api/static/default/inner_content/mp2022.pdf)
and [port/connectivity information](https://www.chennaiport.gov.in/). These are
candidate references; this branch has not verified their acquisition dates,
survey accuracy, georeferencing or redistribution permissions. Proposed works
must be separated from existing structures before importing geometry.

JNPA was selected because the pilot obtained an anonymously queryable authority
GIS with berth/terminal geometry in a documented CRS, an existing application
workflow, and an openly distributed dated Sentinel-2 reference. This is stronger
available source coverage, not proof that JNPA's GIS is survey-accurate.

The generic OSM import accepts `--port INMAA`, `--origin`, source receipt and
version, while the new layer descriptor remains port-neutral. To publish Chennai:

1. Retain a permitted geometry extract and independent dated imagery/authority plan.
2. Check registry identity `INMAA`, choose a local origin and document source clocks.
3. Validate all geometries, terminal names and known dimensions. Preserve unknown
   heights and datum; never clone JNPA geometry or assume matching simulator IDs.
4. Build a new release, source inventory and reference checks, then add a reviewed
   release entry to `catalogue_service.port_directory` and manifest bounds.
5. Supply explicit operational mapping dispositions and run the same API/browser
   tests. Add a new port option only after those assets are available.

The public API currently returns 404 for Chennai. This intentional unavailable
state prevents the UI from presenting repeated generic boxes as a real twin.
