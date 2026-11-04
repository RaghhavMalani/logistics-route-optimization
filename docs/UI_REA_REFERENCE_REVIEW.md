# Restored PortWatch: bounded REA reference review

Reviewed October 30–31, 2026. Local implementation only; hosting deferred. This is an interaction review of the restored application, not a replacement design.

## Capture method and availability

REA MCP tools were absent. Read-only diagnostics found missing Codex registration; the plugin CLI also had an incomplete dependency tree and the default Node version was unsupported. The existing complete, pinned `rea-agents@6.8.0` CLI worked with the bundled Node 24.22.1 runtime. No MCP configuration, native engine or account settings were changed. A redundant `npx` lookup failed DNS; subsequent captures used the already retained package directly.

Each REA scenario launched the installed Chromium 153 executable with an owned blank temporary profile, navigated to the named public URL, waited 2.5 seconds (Windy: 5 seconds), and captured a screenshot and accessibility structure. The first five also captured bounded DOM. There were no sign-ins, private chat/project/payment inspection, external messages, purchases, cookie/storage-value collection or network-body captures. All six Evidence records report `cleanup: terminated-owned-process`.

Raw public captures are ignored under `work/india-intelligence-20261030/rea-references/`; they are not application assets or staged artifacts. Evidence IDs below identify actual CLI results, not registered MCP references.

| Reference and actual URL | Coverage | REA Evidence | Observed scope / limits |
| --- | --- | --- | --- |
| Flightradar24 · `https://www.flightradar24.com/` | UNAVAILABLE | `ev_a6a60aafc2b194856759dd6970e885fb5dbc8798b2ab84eb5029391974d0eefb` | Security verification page; map, inspector and mobile interactions were not observed. No challenge bypass attempted. |
| Claude · `https://claude.ai/` | UNAVAILABLE | `ev_69477d4af7a388e60ded45e623b62b467593317b7b5b3b0ed43633ab0b433845` | Security challenge; artifact/evidence panels and revision interactions were not observed. |
| ChatGPT · `https://chatgpt.com/` | UNAVAILABLE | `ev_6830de352d5a9bb5614cf533771e568f7f657f38da3611e6328900f364daebd8` | Security challenge; conversation/sidebar/recovery behavior was not observed. |
| Codex · `https://chatgpt.com/codex` | UNAVAILABLE | `ev_6ecb486579ff556392fbcfa3f2757a602cd225145b82fbe5c24eb5277edce206` | Security challenge. Native REA UI observation is macOS-only; no supported Windows native observer/selected browser CDP target was available. No Electron identity or private task UI is inferred. |
| Razorpay dashboard, redirected to `https://accounts.razorpay.com/auth/` | PARTIALLY_OBSERVED | `ev_5cbf578a5bc0b844c9e1a2b73b8dabf4e8d199303ee3397fc80bd8a93c7d3157` | Public sign-in form: labelled email/phone input, one Continue action, secondary links. Operational tables, money formatting, authenticated validation and dashboard states were not observed. |
| Windy · `https://www.windy.com/` → public map | OBSERVED, layout only | `ev_f88950ac2455fb49ba08914ab8650f3c4a1bb5efb8816a8b5a4821f628740d5e` | 390×844 live map, compact place context, separate menu control, bottom day/time strip and units. No menu click, keyboard behavior, state retention or performance measurement is claimed. This one optional reference addressed the map/time-control gap. |

The first five used 1366×768. These are runtime navigation/wait captures, not evidence of authenticated product behavior. No marketing screenshot is substituted for an application interaction. No optional second reference was needed.

## Selected changes and their basis

| Current problem | Observation or inference | PortWatch behavior / shared implementation | Workflow risk and acceptance |
| --- | --- | --- | --- |
| Original narrow inspector can obstruct Layers. | Reproduced local issue; Windy's visible map/menu/time separation supports keeping time and layer access discoverable. Phase A was repaired before this reference check; REA did not retrospectively establish the original bug. | `MapPanelAccess`, `FloatPanel`, `TrafficFilters`, `TimeTransport`: narrow inspector headers open the same layer/timeline controls in bounded dialogs. Desktop composition stays intact. | Same chart, workspace filters and selection remain mounted. Normal clicks, Escape, focus return, enlarged text and orientation checks; no forced clicks or duplicated filter state. |
| A revision alert needs exact inspectable evidence and separate source responsibility. | Local dependency contract; Codex/Claude panel patterns remain unobserved. The structured before/after presentation is our inference from PortWatch's review problem. | `CompanyIntelligenceQueue` and `IndianSourceReviewChoices`: consumed/retained IDs, availability and changed fields behind existing disclosures; separate Company source-review action alongside the existing workflow next role. | No rank, equation, recommendation or approval changes. Exact source/voyage links, saved option, return filter and fresh successor review remain explicit. |
| A failed source read hides a previously inspected result or invites an ambiguous retry. | Local failure case; Razorpay's public form supports one clearly labelled primary action only. Authenticated error recovery was not observed there. | `NavigationRestrictionPanel`: retain the previous result with an explicit failure label and Retry retained source read action; unavailable exact IDs offer an explicit clear selection action. Existing form acknowledgement gates the fictional declaration. | Retained results are not newly verified. Controlled 503 injection tests normal retry without a provider request or automatic source adoption. |

No third-party branding, fonts, bundles, assets, aviation features, assistant shell or trading UI were copied. No new UI dependency or animation was introduced. Signed slack, unknown values, historical sources, modeled/partial amounts and simulated-outcome labels remain visible.

## Product evidence

Matched old/new queue screenshots use the preserved prior build on port 4213 and the integrated build on port 4214, the same synthetic projection, selected row, open disclosure and viewport. They are fixture presentation evidence, separate from actual NHO/local-visitor screenshots. Before/after pairs and interaction results are retained under ignored work storage. Mobile Layers checks use actual local visitors and shared workspace state.

Validation results and remaining source limits are recorded in [the integrated milestone](INDIAN_PORT_INTELLIGENCE_AND_RELIABILITY.md). A REA reference capture is not product acceptance, measured UX improvement or operational evidence. The blocked references remain unavailable; this milestone does not claim their authenticated behavior was reconstructed.

The final combined product run passed 30 browser cases with retries disabled at desktop, 390px and 360px. It checks normal pointer and keyboard use, exact links, disclosures, retained errors, enlarged text, orientation, four-role navigation, source audit parity and globe/chart return. Source, queue and declaration screenshots are separately labelled real-source/local-session or synthetic fixture evidence. Earlier harness/startup failures and their corrections are recorded in the integrated milestone rather than omitted from the validation history.
