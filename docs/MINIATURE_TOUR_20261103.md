# PortWatch X miniature tour

3 November 2026, Asia/Kolkata. First visual review unit, based on
`350b14a4d04e4046489e528bca9c6b9c20a40921`, branch `feat/miniature-tour`.
The integration checkout and its nineteen activity/history CSV changes and
`debug.log` are preserved. This work uses an isolated worktree. It neither
promotes production nor changes hosting configuration.

## Product and module boundary

`/tour` is a public, full-screen, backend-independent route. `/` retains its
existing redirect. Public navigation and sign-in have a quiet tour link. The
four operational roles and their workflows remain the existing application.
The whole-app miniature theme is the subsequent review unit; this page alone
does not complete that milestone.

`components/miniature` contains React-free materials, lighting, deterministic
RNG and reusable ship, quay-crane, gantry, truck-part, yard, tree and track
builders. `components/tour` owns the illustrative composite, camera, chapter
data and overlay. The route lazily loads the page and scene. Three.js and the
builders are not imported by login or the unrelated route entry.

The root omits AuthProvider and WorldProvider on `/tour` and `/tour/`; it does
not merely suppress an error after restoring a saved session. All other routes
retain the existing providers. Visitor sessions remain stored normally and
restore on returning to an operational route. There is no new auth bypass on
an operational screen.

The scene owns a fresh canvas per effect setup, including React development
effect replay. Cleanup cancels RAF, removes listeners, disconnects observers,
disposes instanced meshes, shared/cloned geometries and materials, shadows and
renderer, loses the owned context and removes that canvas. Hidden tabs pause.
Reduced motion freezes movement and redraws only for controls or resizing.

## Reference fidelity and differences

The supplied 913-line HTML was ported from source, retaining seed `20261102`,
RNG consumption order, geometry, object sizes, lane and option paths, six
camera keyframes, pin coordinates and the following shadow camera. Containers,
trees, road dashes, truck parts, trains and wagons remain instanced. The video
was inspected as inspiration; no reel frames, third-party branding or bundles
are product assets. The downloaded and pasted Markdown have identical lines;
their final-newline difference does not change the specification.

Intentional changes:

- Installed runtime is Three.js **0.186.0**, types **0.185.4**. sRGB output and
  NoToneMapping are explicit. r186 removed PCFSoftShadowMap, so supported
  PCFShadowMap is used. Hemisphere/sun intensities were compared with actual
  reference frames and retuned from the suggested 2.2/2.4 to **3.3/3.6**.
- Normal painting is bounded to 30 fps, 24 below 640px, retaining the reference
  elapsed-time motion, 0.05s clamp and `1-exp(-dt*3.4)` camera damping. DPR is
  capped at 2/1.5; shadow maps are 2048/1024. ResizeObserver handles sizing.
- Ship instance capacity covers the reference's possible fourth tier without
  writing beyond the buffer. Active instance placement and RNG order are
  unchanged.
- Text-bearing actions use `#c9461a`; the model retains `#ee5a24`. White on the
  former is approximately 4.80:1, versus 3.43:1 on the reference orange.
- The narration explicitly retains content-box geometry under Tailwind's
  border-box reset. Pins have 32px targets. Popovers can appear above the card,
  have a close control and return focus on Escape. The demo link retains its
  complete accessible name when its visible label shortens.
- The exact portrait camera puts two decision pins outside the viewport. A
  compact chapter-point disclosure preserves all four explanations on narrow
  screens and all hotspot content when WebGL is unavailable. World pins still
  hide offscreen instead of being moved to invented positions.
- Tour CSS is linked in the document head to avoid an unstyled first paint.
  Unmodified Archivo and IBM Plex Mono Latin font subsets are local, preloaded
  and use optional display with fallbacks; licenses, provider URLs and hashes
  are retained under `public/fonts`. This avoids a late external font swap.

The tour remains an invented composite. It is not an operational port layout,
survey, traffic observation, booked rail service or live berth plan. The actual
port-twin geometry and bindings are not replaced by it.

## Claims and evidence

Copy separates source reports, forecast context, inferred exposure and operator
assumptions. It makes no universal live-feed/corroboration claim, verified
capacity claim, automatic learning-adoption claim or cross-visitor Admin claim.
Approvals and demo outcomes are not external execution.

The original historical synthetic benchmark is identified precisely. The
retained `outputs/benchmarks/decision_benchmark.json` test suite has 200 VESSEL
cases, seeds 5001–5200 and 10 unscored cases. Its aggregate reports BALANCED
mean/p90 regret **12.14/42.1 h**, versus ROBUST **1.05/0.0 h**. These match
[the dated original gate](DECISION_POLICY_GATE.md), not measured shipping
savings or a newly untouched test. The current-plan baseline also has 1.05 h
mean regret in that corpus. The tour links the immutable original gate, whose
limitations remain inspectable. No benchmark is rerun or model promoted.

Registered port count is 13, role count four. The five illustrated berth-policy
comparisons are implemented in `decision/port.py` over the existing twin.
Those counts are software descriptions, separate from benchmark figures.

## Local verification and inherited failures

TypeScript, a Vite/Nitro production-format build and changed-file ESLint pass.
The full lint comparison against the base reports **1,496 inherited errors**:
1,452 formatting findings, 42 explicit-any findings and two obsolete fixture
hook findings. There are 49 warnings and no errors in the changed/new files.
The base has 1,517 errors; formatting the touched login removes 21. Checkout
CRLF was normalized locally for the comparison, without broad source changes.

The tour's four browser contracts run at 1920×1080, 1366×768, 390×844 and
360×800. They cover actual render calls, all chapters, chapter-3 navigation,
desktop decision pins/narrow indexed explanations, popover Escape/focus,
overflow, console/page errors, blocked application APIs with a restorable
stored session, the trailing-slash route, reduced motion, unavailable fonts,
WebGL fallback and five login round trips per viewport. A negative control
confirms that the same stored session does restore outside the tour.

The existing public-route run against an isolated verified-API backend reports
**24 passed, eight failed and six not run** across 38 cases; its 16 tour cases
overlap the dedicated run and are not additional independent cases. Eight
other public/research cases passed. Failures target the removed “Investigate
the world.” heading, its old error copy/list, and the former arrival block on
Port Operations. Three serial arrivals checks per viewport did not run after
the first obsolete-screen assertion failed. The relevant application modules
are unchanged from the base; no source collection failure is hidden as success.

The old guards suite reports **14 passed, 68 failed** across 82 cases. Its
`qa/harness.ts` still seeds a local demo session without an access token and
does not replay `/demo/session`; this cannot authenticate the current
server-managed demo adapter. One assertion explicitly expects asserted rather
than verified identity. Anonymous redirects and invalid-password refusal pass.
These are inherited fixture/security-expectation failures, not a reason to
weaken restored authentication. Actual four-role hosted checks remain required
for the integrated theme release.

Raw logs and reference frames are ignored under `work/miniature-20261103`.
Only the selected API-free illustrative tour captures under `qa/fixtures/tour`
are intended Git image deliverables. They contain no sessions or private
commercial data.

Final production-auth tour verification passes **16/16 cases**, without retries.
Earlier development runs overlap this matrix and are not additional evidence
samples. There are zero application API requests on direct `/tour` and
`/tour/` loads with a restorable saved visitor; the login negative control does
make its expected session-restore request.

Matched production-auth builds fetch **498,419 → 499,307 bytes** of JavaScript
on cold `/login` navigation (**154,763 → 154,965 gzip bytes**, +888/+202).
The login does not fetch TourScene or Three.js. `/tour` fetches 985,381 decoded
JS bytes, 278,748 gzip bytes, including its intentional lazy renderer. Measured
desktop tour CLS is **0** with the local preloaded fonts and head-linked CSS.
This is a browser PerformanceObserver measurement, not a claimed Lighthouse
score or a hosted latency benchmark.

## Verified anonymous tour checkpoint

Verified at **2026-11-02 20:36 UTC**, 3 November 02:06 Asia/Kolkata:
[public tour](https://india-portwatch-epvtb6k88-flash2404s-projects.vercel.app/tour).
Vercel deployment `dpl_4BQXSkSmYe3DVw3uaioif6FrNU9s` is READY, Preview
(`target=null`), has no assigned aliases and carries frontend source
`858865d77ece7bfec0a26da6d2e2c4e73f388ae6`, fingerprint
`af68d2aa482d6beefa1bbaff82aa94a261382c7d2f4434aee7e1ae739370570a`.
[PR #7](https://github.com/RaghhavMalani/logistics-route-optimization/pull/7)
targets the integration branch, not main.

Eight hosted tour cases passed without retries at 1366px and 390px, in fresh
anonymous browser contexts with no hosting bypass. HTML, release JSON, local
font and same-origin health returned 200 with the expected content types. The
source-products operational endpoint correctly returned application JSON 401
without a verified session; this is not Vercel protection or a site outage.

This is deliberately a **frontend-only tour checkpoint**. Its existing
isolated API remains verified `a80a42768e84ebced9a08bdee16feca918dd7fd7`,
service `c7dfe1db-2fd0-4c24-8a59-dde1d34239c2`, environment
`678352b2-e032-4c0c-b900-60f68fa3562f`, deployment
`cc20087c-805a-4e6e-ad0c-b15b9454765d`. Direct and proxied release identities
match. No backend restart, collector update or production promotion occurred.
The complete theme/capability release still requires a new documented unified
source revision and final role/workflow/recovery acceptance.
