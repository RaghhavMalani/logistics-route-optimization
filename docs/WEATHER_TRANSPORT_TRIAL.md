# Railway preview weather transport trial

The baseline used the isolated weather preview on commit `537d873c7ef32fcffc3bf26e8a243718e8c5df73`. The measurements are from that container and its refresh journal and snapshot archive.

## Network diagnosis

The matrix ran at 19:50 IST on 16 November 2026. Timings are elapsed from TCP connection start unless stated otherwise.

| Check | Surface, api.open-meteo.com | Marine, marine-api.open-meteo.com |
| --- | --- | --- |
| DNS A | `51.81.167.44` | `152.53.84.37` |
| DNS AAAA | None | `2a0a:4cc0:c0:2004:a820:cbff:fea6:1fc` |
| Actual Requests address family | IPv4 | IPv4 |
| IPv4 with TLS 1.2 | HTTP 200, curl appconnect 64–65 ms | HTTP 200, 634–645 ms |
| IPv4 with TLS 1.3 | HTTP 200, curl appconnect 43–44 ms | HTTP 200, 480–527 ms |
| HTTP/1.1 forced vs HTTP/2 offered | HTTP/1.1 and 200 in both modes | HTTP/1.1 and 200 in both modes |
| IPv6 only | No DNS answer | TCP failed with network unreachable |
| ServerHello | 39–41 ms | 474–507 ms |
| Certificate message complete | 39–41 ms | 478–514 ms |
| Chain as sent, DER | 4 certificates, 3,393 bytes | 3 certificates, 4,053 bytes |
| TCP maximum segment size of 1,200 bytes | Similar timings to default while healthy | Similar timings to default while healthy |

The 15 November incident showed two surface attempts with TCP established in 19–20 ms and a TLS handshake timeout after eight seconds. The successful matrix cannot locate the point in the handshake where those attempts stalled. Marine sent the larger chain. The reduced-segment test did not exercise a stalled path. A path-MTU black hole therefore remains unconfirmed. The surface collector can explicitly use IPv4, which both the working surface path and the existing client already use. Neither TLS version showed a failure during the matrix.

## Baseline and scoring

The baseline contains the 12 complete UTC hours from 16 November 15:00 UTC through 17 November 03:00 UTC. Each HTTP attempt is counted once. A delivery cycle succeeds if all 13 ports have an archived response fetched during that UTC hour with finite values for all five surface fields in that hour. Retained forecasts that still cover that hour are tracked separately. The availability-policy column uses the immutable first receipt of the current forecast values, which the app uses to label weather stale after one hour. Repeated successful checks with identical forecast values do not change that instant.

| Preview phase | Valid delivery attempts | All-port delivery cycles | All ports inside availability policy at close | HTTP 429 |
| --- | --- | --- | --- | --- |
| 1. Single 13-port request | 4/20 (20.0%) | 4/12 (33.3%) | 0/12 | 0 |
| 2. Four groups via Railway | 27/273 (9.9%) | 3/12 (25.0%) | 1/12 | 0 |
| 3. Four groups via Vercel Preview | 48/48 (100%) | 12/12 (100%) | 2/12 | 0 |

All 16 baseline errors were timeouts. The eight hours without any successful delivery still had retained data for all ports. On JNPA, the four new receipts preserved the identical values first received at 20:13 IST on 16 November.

Run the scorer from the repository root on the preview container with `python -m scripts.measure_surface_preview --state /app/state --start 2026-11-16T15:00:00Z --end 2026-11-17T03:00:00Z`.

## Direct transport candidate

The surface scheduler splits the 13 ports into groups of 4, 3, 3 and 3. It runs them sequentially over a persistent, certificate-verified HTTPS connection. When it reconnects, it offers a saved TLS session where the TLS adapter supports resumption, resolves IPv4 again and advances through the available A records. TCP and TLS share a three-second budget after DNS lookup. The HTTP socket has an eight-second timeout. Only TCP/TLS timeouts cause up to four immediate retries, with jitter. A 429 stops the remaining groups and honours the provider's retry deadline through the existing persistent circuit breaker.

The scheduler keeps successful groups and only requests missing groups on another scheduled attempt in the same hour. It records individual HTTP attempts on both successful and failed runs. The original forecast bytes, per-port location binding and availability timestamps remain available for evidence and labelling.

The candidate `a5b9395613e8477c294aff405d5a7587338eb01f` ran from 17 November 09:00 UTC through 21:00 UTC. It delivered valid responses in 27/273 HTTP attempts (9.9%) and covered all 13 ports in 3/12 hours (25.0%). An additional five hours delivered 9/13 ports. One hour ended with all 13 inside the app's availability policy. There were 234 TCP/TLS timeouts, 12 disconnects and zero HTTP 429 responses. The candidate missed the 98% cycle gate.

## Vercel relay candidate

The isolated Railway scheduler triggers the separate Vercel preview function at the usual collection times. Vercel Cron runs on production deployments, and its Hobby frequency is daily, so it cannot provide an hourly preview trial. The function is projected to cost $0 within the Hobby allocation of one million monthly function invocations. Four groups per hour give 2,976 invocations per 31-day month before retries. [Vercel Cron scheduling](https://vercel.com/i/event-driven-architecture) · [Vercel Hobby allocation](https://vercel.com/docs/plans/hobby).

The function accepts only signed collection requests and fetches the fixed Open-Meteo endpoint. It signs the original response bytes, group and timestamp for the Railway callback. The callback applies the same forecast validator as direct collection and retains the raw bytes. The provider remains Open-Meteo. A separate `via relay` field records delivery. Both hosts read the HMAC secret from their Preview environment. The Railway route returns 404 when the relay is disabled.

For the trial, one reported attempt is one requested group delivery. `relay_unconfirmed` records the cases where Railway cannot confirm that the function ran or that Open-Meteo was reached. Confirmed provider timeouts and callback errors have separate counters.

### Completed relay trial

The measured SHA was `9134c676180dc43da361c946eac46cbc05f1613f`. The 12-hour window was 18 November 2026, 09:30–21:30 IST (04:00–16:00 UTC). All 48 requests produced signed, validated group deliveries, with zero HTTP 429 responses, provider timeouts, callback errors or unconfirmed attempts. All 13 ports had data delivered in each cycle. The manual end-to-end check happened before the window. At the final check the preview service and scheduler were healthy and all 13 latest port receipts reported `via relay`.

Only two cycle closes had all ports within the app's one-hour availability policy. In the other ten the provider returned the same forecast values already on file, so validation succeeded while the original first-availability dates stayed intact. The application continued to label those forecasts stale. The relay met the 98% delivery target in this trial. There were no missed Open-Meteo cycles to trigger MET Norway.

The separate relay project is disconnected from GitHub and uses a project-scoped automation credential to reach its protected Preview function. Vercel classified the project's first upload as Production despite the Preview option. That unused deployment was removed. The trial used Preview deployment `dpl_99ekJQTPFEQcuUfuW2NkCFETpf2j`, which targeted the isolated Railway preview for every callback. [Vercel's first-deployment behaviour](https://github.com/vercel/vercel-plugin/blob/main/commands/deploy.md).

Local evidence is under `work/weather-transport-20261116/` in the parent workspace. `RELAY_12H.json` records the complete hourly and attempt counts. `RELAY_FINAL_HEALTH.json` confirms the running service and source distinction.

## Pull relay hardening, 19 November

During the 9134c67 trial, the existing Railway single-owner freshness coordinator invoked `current_surface_batch` once per UTC hour. Its `surface_run` called four sequential port groups. Each invocation authenticated a POST to the Vercel Preview function. The function fetched Open-Meteo and posted a signed callback to Railway. Vercel Cron did not invoke any trial request.

The hardened relay returns signed original bytes to the waiting Railway scheduler. Each request has a cryptographically random challenge. The response signature covers that challenge, group, timestamp and full envelope, including the fixed provider identity and raw response. The backend rejects a mismatched challenge, a timestamp older than five minutes, a future timestamp beyond 30 seconds and any signature mismatch before parsing weather data. The callback route is removed.

The relay's generated query allow-list contains only the registered port coordinates and six fixed forecast parameters. Its exporter has a freshness check against the Python registry. Unknown fields and changed coordinates are rejected before any upstream call. Authenticated requests are limited to one call per group per 30 seconds per warm function instance, with a five-minute nonce replay cache capped at 256 entries. The Railway scheduler remains single-owner and uses a durable retry circuit. The function limiter is local to a warm instance and is additional to those scheduler limits.
