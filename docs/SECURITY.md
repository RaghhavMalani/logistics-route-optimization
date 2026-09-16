# Security model

The release candidate's security review: what the API believes about who is
asking, what each role may reach, what was attacked and how it held, and what
is left. Findings are numbered; each names the fix or the reason it stands.

## 1. Identity

Identity reaches the API as headers the terminal sets from its session:
`X-PortWatch-Role`, `X-PortWatch-Actor`, `X-PortWatch-Port`, `X-PortWatch-Org`,
`X-PortWatch-Vessels`. **Nothing verifies a token.** `backend/app/identity.py`
is the seam a verifier replaces; `/api/advisories/policy` and
`/api/admin/readiness` say so on every deployment. Two modes:

| mode | missing role | for |
|---|---|---|
| `asserted` (default) | national command, except on administration surfaces | a demo on a private network behind the terminal; a checkout; the in-process tests |
| `required` (`PORTWATCH_IDENTITY_MODE=required`) | 401 at the door (middleware), on every `/api/*` route but health, provenance, the policy statement and the docs | a deployment behind an authenticating proxy that sets the headers from a verified session and strips what the client sent |

Two rules hold in both modes:

- an administration surface needs `X-PortWatch-Role: NATIONAL_ADMIN` present;
  a missing header is 401, never a promotion;
- administrator standing follows the role alone. `X-PortWatch-Admin` is not
  honoured (finding 3).

Readiness carries `identity_mode`; a COMMERCIAL or GOVERNMENT licence mode in
`asserted` identity mode is a WARN there.

## 2. Authorization matrix

`ALLOW`: the role gets the resource. `DENY`: 401 with no identity, 403 with
the wrong one. `SCOPED`: filtered to what the identity holds; a probe of
another tenant's record is 403. `NONE` is a request with no headers in the
default mode. `tests/test_authorization_matrix.py` probes every cell and
checks this table against the code.

| resource | method | path | NONE | NATIONAL_ADMIN | PORT_AUTHORITY | SHIPPING_COMPANY | VESSEL_OPERATOR |
|---|---|---|---|---|---|---|---|
| WORLD | GET | `/api/world/state` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW |
| WORLD | GET | `/api/world/cascades` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW |
| WORLD | POST | `/api/world/branches` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW |
| WORLD | POST | `/api/world/clock` | DENY | ALLOW | DENY | DENY | DENY |
| AIS | GET | `/api/world/ais/tracks` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW |
| AIS | GET | `/api/fabric/health` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW |
| ATTENTION | GET | `/api/attention` | SCOPED | ALLOW | SCOPED | SCOPED | SCOPED |
| DECISIONS | GET | `/api/decisions/actions` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW |
| DECISIONS | GET | `/api/decisions/problems` | SCOPED | ALLOW | SCOPED | SCOPED | SCOPED |
| DECISIONS | POST | `/api/decisions/problems` | DENY | DENY | ALLOW | DENY | DENY |
| DECISIONS | POST | `/api/decisions/problems` | ALLOW | ALLOW | ALLOW | ALLOW | DENY |
| FINANCIAL | GET | `/api/finance/basis` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW |
| FINANCIAL | GET | `/api/finance/tariffs` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW |
| FINANCIAL | POST | `/api/finance/assumptions` | DENY | ALLOW | DENY | DENY | DENY |
| FINANCIAL | POST | `/api/finance/assumptions/clear` | DENY | ALLOW | DENY | DENY | DENY |
| ADVISORIES | GET | `/api/advisories` | DENY | ALLOW | SCOPED | SCOPED | SCOPED |
| ADVISORIES | GET | `/api/advisories/policy` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW |
| ADVISORIES | POST | `/api/advisories` | DENY | ALLOW | ALLOW | DENY | DENY |
| MISSIONS | GET | `/api/missions` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW |
| MISSIONS | POST | `/api/missions/suez-ever-given-2021/replay` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW |
| ADMIN | GET | `/api/admin/freshness` | DENY | ALLOW | DENY | DENY | DENY |
| ADMIN | GET | `/api/admin/readiness` | DENY | ALLOW | DENY | DENY | DENY |
| ADMIN | POST | `/api/admin/freshness/marine/refresh` | DENY | ALLOW | DENY | DENY | DENY |
| LEARNING | GET | `/api/learning/summary` | ALLOW | ALLOW | ALLOW | DENY | DENY |
| LEARNING | GET | `/api/learning/policies` | ALLOW | ALLOW | ALLOW | DENY | DENY |
| LEARNING | GET | `/api/decisions/learning` | DENY | ALLOW | DENY | DENY | DENY |
| LEARNING | POST | `/api/learning/run` | DENY | ALLOW | DENY | DENY | DENY |
| LEARNING | POST | `/api/learning/backfill` | DENY | ALLOW | DENY | DENY | DENY |
| DIAGNOSTICS | GET | `/api/admin/diagnostics` | DENY | ALLOW | DENY | DENY | DENY |
| AGENTS | GET | `/api/agents/tools` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW |
| LENSES | GET | `/api/security/lens` | ALLOW | ALLOW | ALLOW | ALLOW | ALLOW |

Scoping rules (`backend.app.identity.may_see_decision`, the advisory store's
`visible_to_recipient`):

- **decisions** -- national command sees every decision; a port authority the
  decisions of its own port (those it holds, and a berth decision whose
  subject is its port); a shipping company the decisions its organisation
  holds; a vessel operator the decisions about its own hulls and its
  organisation's. Read, list, transition, hand-off and outcome all apply it,
  and so does a record restored from the ledger. The listing applies it
  inside the ledger query, before the page, so a tenant's rows behind other
  tenants' newer ones are found without reading a body. A company or
  operator that names no organisation, or a port authority that names no
  port, is refused a new decision (400) rather than handed one that its own
  scope could never read back.
- **advisories** -- an issuer sees what it issued at its port; a recipient sees
  what was issued to its vessels once ISSUED, never a DRAFT.
- **attention** -- each role's queue is framed for its scope.
- **domains** -- a berth decision is held by a port authority; a cargo
  decision by a shipping company (or an adviser mapped onto it); a routing
  decision by a company, an operator, or an adviser. Anyone else is 403.

## 3. Findings

| # | severity | finding | disposition |
|---|---|---|---|
| 1 | HIGH | A request with no role header was national command everywhere, administration and diagnostics included. | Fixed: administration surfaces require the role present (`resolve_role(admin_surface=True)`); `required` mode refuses a missing role at the door. Test: `test_no_identity_never_reaches_an_administration_surface`. |
| 2 | HIGH | The learning surfaces (`/learning/*`, `/decisions/learning`) were open to every role, including `POST /learning/run` and `/learning/backfill`, which write the ledger. | Fixed: reads for national command and port authorities; the writes and the cross-tenant decision score for national command only. |
| 3 | HIGH | `X-PortWatch-Admin: 1` on any role granted administrator standing on advisories and policy approval. | Fixed: standing follows the role; the flag is ignored and `/advisories/policy` says `adminFlagHonoured: false`. Test: `test_the_admin_flag_grants_nothing`. |
| 4 | HIGH | Any named actor could read, list, transition, hand off or record an outcome on any decision in the process, across tenants. | Fixed: every decision route applies `may_see_decision`. Tests: `DecisionScopeTests`. |
| 5 | MEDIUM | `POST /finance/assumptions` let any role change the process-wide cost basis that prices every tenant's decisions. | Fixed: national command only; a carrier prices its own scenario with `assumptions` on the decision request, which stay on that problem. |
| 6 | MEDIUM | `POST /world/clock` resolved the role with the default, so a request with no headers could move the process clock. | Fixed: administration surface. |
| 7 | MEDIUM | A NaN coordinate, a NaN cascade offset, a non-numeric mission offset and a ±10¹² h seek each produced a 500. | Fixed: finite checks, list bounds (64 offsets, 500 waypoints), a ±366-day seek bound, a 1990-2100 instant window. Tests: `tests/test_api_fuzz.py`. |
| 8 | MEDIUM | A cost rate or an FX rate accepted zero, negative, NaN, infinite and boolean values, and any string as a currency. | Fixed at the model: `CostRate` and `FxObservation` require a finite positive number and an ISO-4217 code; the routes refuse a non-numeric JSON value before conversion. |
| 9 | LOW | A hostile port code is reflected in the 404 detail. | Stands: the detail is JSON, the terminal renders it as text. |
| 10 | LOW | A blank `portCode` on a berth decision falls back to the port the identity speaks for. | Stands, by design; documented in the fuzz test. |
| 11 | INFO | `subprocess` is used once (the pipeline refresh): fixed argv from environment variables, no shell, no request input. `ast.literal_eval` on cached data only. No pickle, no `yaml.load`, no dynamic SQL with request input (table and column names are code constants; values are parameters). Route parameters index dictionaries, never build paths. | Reviewed; no change. |
| 12 | INFO | Secrets: `AISSTREAM_API_KEY` and `OPEN_METEO_API_KEY` are read on the server, `/admin/*` payloads are scrubbed against their values, and the fuzz suite asserts no response carries a configured secret. Nothing logs a key. | Reviewed; no change. |
| 13 | INFO | CORS: `PORTWATCH_CORS_REGEX` defaults to localhost; production sets the exact terminal origin. Every mutating request carries custom `X-PortWatch-*` headers, so a cross-site request is preflighted and refused unless the origin matches. | Reviewed; documented. |
| 14 | INFO | MCP: the server withholds EXECUTE at the default ceiling (CI asserts the catalogue); agent tool access follows the identity headers. | Reviewed; no change. |

## 4. What was attacked

`tests/test_api_fuzz.py` fires malformed input at every request-facing
route -- coordinates, money, currencies, scenario options, decision ids,
mission clocks, world timestamps, vessel ids, four-megabyte and 400-deep
bodies, raw `NaN`/`Infinity` tokens, negative rates, extreme dates, hostile
identity headers -- and asserts every answer is a 4xx with a JSON detail or a
2xx, inside 30 s, with no traceback, no file written into the source tree and
no configured secret echoed. Findings 7 and 8 came from it.

## 5. Dependencies

`pip-audit` on `requirements.txt` and `requirements-extras.txt`: no known
vulnerabilities (36 packages). `npm audit` on the terminal: five findings,
four fixed by `npm audit fix` within their declared ranges (brace-expansion,
js-yaml, nanoid, postcss -- transitive build-time dependencies). One stands:

| package | severity | advisory | disposition |
|---|---|---|---|
| maplibre-gl 5.24.0 | critical | XSS sanitizer bypass in `DOM.sanitize()`; fixed in 6.9.1 | **Unresolved.** The fix is a major upgrade (5 → 6). The vulnerable path is `Popup.setHTML` / attribution HTML; the terminal uses neither (`attributionControl: false`, no Popup, no Marker, no `setHTML`), so no untrusted HTML reaches the sanitiser. Upgrade as its own change with the map regression suite, not inside the release freeze. |

## 6. What this deployment does not claim

- It does not authenticate anyone. Behind the terminal on a private network,
  or behind a proxy that verifies a session and sets the headers, it enforces
  the matrix above against the identity it is handed. On the open internet
  with no proxy it enforces nothing, and readiness says so.
- Tenant isolation is by scoping rule, not by storage: one ledger, one
  advisory register, one basis. A national administrator sees everything by
  design.
- Rate limiting and request quotas are the proxy's job; the API bounds the
  size and shape of what it will parse (findings 7-8) but does not throttle.
