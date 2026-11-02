# Local free-source coverage

Checked 2 November 2026. This is a local, noncommercial research profile. It does
not describe the currently hosted version. A configured product is not proof of
current observations; the UI displays its actual retained state.

| Product | Actual local evidence | UI and calculation boundary | Remaining limit |
|---|---|---|---|
| Open-Meteo surface and marine | Genuine hourly responses retained for registered Indian ports; Paradip, Chennai and JNPA manually checked at 02:28 UTC on 2 November; further ports collected by the scheduler | Current-input inspector and frozen hourly approach comparison; raw forecast hashes and target times retained | Forecasts, not measurements. Daily corrections do not alter hourly gust/visibility |
| Paradip official vessel reports | Existing collector ran against the official source in the isolated profile; working/anchorage/ready rows remain explicitly scoped | Port operational context, original report dates and receipts, operator-declared criterion | Periodic reports do not establish berth availability or individual waiting |
| Chennai official position/ETA PDFs | Current attempts failed certificate-chain verification | Unavailable/error with retained history | TLS validation remains enabled; no generated replacement |
| GDACS | Existing retained collector and thirty-minute local schedule | Regional hazard context and source archive | A regional alert is not a port closure or calculated delay |
| USGS all-day earthquakes | 200 rows in first manually retained response, 02:27:57 UTC; subsequent scheduled checks observed | Public products and globe context; event/update/receipt clocks separate | No damage, closure or delay inferred |
| GDELT maritime discovery | Bounded topic request repeatedly timed out | Public product failure/last-good state; source-linked discovery if available | Discovery alone is not corroboration or a disruption probability |
| FRED DEXINUS | 30 dated INR/USD observations retained at 02:28:06 UTC | Economic reference context; original date precision retained | Not an executable quote or a forecast; no automatic currency conversion |
| FRED DCOILBRENTEU | 30 dated USD/bbl observations retained at 02:28:06 UTC | Economic reference context | Brent is not a delivered vessel bunker price |
| IMF PortWatch daily Paradip aggregate | Current bounded API query unqualified; provider returned invalid-query response | Explicit unavailable state; older archive remains inspectable | No current individual waiting or berth observation established |
| UN Comtrade no-key annual preview | One 2025 India/world HS1006 import record retained at 02:28:22 UTC | Dated structural market context and commercial example evidence hash | Annual, limited preview; no invented buyer, destination demand or invoice |
| LMA/JWC JWLA-035 | Original four-page 16 September 2026 PDF retained; first receipt 02:27:56 UTC, SHA-256 `b8f927604ecefa4ca27aa3c9574f96d41459b3de32b58fbfc958ae3ca627439a` | Historical listed-area context and insurance review | Geometry requires boundary review. No closure, premium, probability or coverage determination |
| AISStream | Server-side integration, bounded three-box subscription, actual normalizer and safe DTO tested; no authorized live observations established in this run | Explicit provider traffic view and observed-vessel inspector; scenario replay separately selectable | Missing access/coverage remains unavailable; no simulated AIS fallback |
| CCTV | Existing authorized-media boundary retained | Camera registry / reviewed observations | No newly authorized operational footage; no claimed CV accuracy |

The seven entries in the new public-products panel are a scoped denominator
(USGS, GDELT, two FRED series, IMF, Comtrade and JWC), not a percentage of the
application that is real. Weather, port reports and AIS have separate producers.

## Truth and lifecycle

Typed origin, freshness and execution fields are separate. Each retained product
keeps source/reference/target precision, first availability, last successful
check, raw response hash, coverage, units and limitations. Identical responses
preserve first availability. Failed or unqualified checks retain their original
response separately and do not renew the last qualified value. Replay withholds
data first available after its clock. Read-only GETs neither collect nor create
feedback samples. Private paths, transport errors containing credentials and
financial/session data are excluded from public DTOs.

The opt-in process uses the existing freshness coordinator: surface/marine per
registered port hourly, GDACS every 30 minutes, USGS every five minutes, GDELT
every three hours, FRED/IMF daily and Comtrade/JWC weekly. Each scheduled public
product has at most two attempts per cycle. Thirteen ports × two weather products
is about 624 nominal weather requests/day, before bounded retries and separately
limited reconciliation. This is a request budget, not evidence of day-long uptime.
Local collection runs only while its process runs; no Windows task or Codex
automation was created. The authorized isolated hosted preview reuses this same
coordinator under `PORTWATCH_RESEARCH_SOURCE_PROFILE=1`, with one always-running
worker and replica; it adds no scheduler service. An exclusive file lock prevents two
collector owners using the same local state. Global activity CSV refresh is off.

Keep `AISSTREAM_API_KEY` in the server environment only, if authorized access is
available. Never put it in frontend variables, committed files or screenshots.
The optional recorder writes into ignored local state. Current source labels
require actual valid recent observations, not the presence of a key.

## Access conditions

Open-Meteo's free endpoint is for noncommercial use, has published request limits
and requires attribution. Marine data is not a navigation service. AISStream
requires a server-held key and bounded subscription. Comtrade's no-key preview is
limited and its data-use policy still applies. Publisher rights apply to news
and dated circulars. This profile does not grant commercial redistribution rights.

- [Open-Meteo pricing](https://open-meteo.com/en/pricing), [terms](https://open-meteo.com/en/terms), [marine documentation](https://open-meteo.com/en/docs/marine-weather-api)
- [AISStream documentation](https://aisstream.io/documentation)
- [UN Comtrade API](https://uncomtrade.org/docs/un-comtrade-api/), [data-use policy](https://uncomtrade.org/docs/policy-on-comtrade-data-use/)
- [LMA listed areas](https://lmalloyds.com/specialist-areas/underwriting/listed-areas/)

Actual public receipts and scheduled attempts are in ignored local logs and
immutable archives. Fixture-based contract tests demonstrate software behavior;
they do not turn unavailable services, forecasts, simulation or shadow models
into confirmed operational outcomes. Weather feedback remains collecting where
independent matured targets and chronological validation are insufficient. Both
previously rejected neural/RL candidates remain rejected.
