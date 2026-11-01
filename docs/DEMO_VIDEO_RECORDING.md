# Local current-source demonstration

November 1, 2026. Local review and export only. Hosting, production volumes, public aliases and the dated October 26 hosting package are unchanged. Media, raw takes, private visitor state and portable tools remain in ignored `work/current-source-demo`; they are not Git deliverables or public uploads.

## Deliverables

- `work/current-source-demo/video/final/portwatch-demonstration.mp4`: silent H.264 recording of the actual local application. Active actions retain ordinary playback speed; explicitly labelled reading pauses hold real frames.
- `work/current-source-demo/video/final/captions.vtt`: synchronized English captions.
- `work/current-source-demo/video/final/chapters.txt`: final chapter times.
- `work/current-source-demo/video/final/poster.png`: an actual source-scene frame.
- `work/current-source-demo/video/final/manifest.json`: sanitized source/build, capture, evidence, edit and delivery hashes.
- `work/current-source-demo/video/final/edit-plan.json`: chronological source intervals, retained results and caption text.
- `work/current-source-demo/video/final/player.html`: local player with captions. Run `python scripts/serve_demo_video.py` and open `http://127.0.0.1:8921/player.html`. This loopback-only server supports byte ranges for browser seeking and serves only the final deliverable filenames.

The narration is in [DEMO_VIDEO_SCRIPT.md](DEMO_VIDEO_SCRIPT.md). No recorded or synthetic voice, AAC track or music is claimed. The catalogue [SHIPPING_SCENARIO_CATALOGUE.md](SHIPPING_SCENARIO_CATALOGUE.md) documents S01–S26, including unsupported cases; it does not claim 26 filmed screens. The cargo-arithmetic insert is a separately selected fictional S16 call with its own UTC schedule and evidence IDs, clearly identified in the captions/manifest; it does not replace the main source-bound advisory's identity.

## Meaning of the demonstration

The real source is the November 1 Paradip Port Authority daily traffic report, discovered through the existing official catalogue and PublicPilot. Original SHA-256: `490e48be581f3e377c028395c56bc919a883e99ce628031ea4517b29cc87f0fe`. First receipt: `2026-11-01T07:44:49.320498Z`; available parse/successful check: `2026-11-01T07:44:57.356053Z`. The working section lists 22 named rows, including repeated names across berths and completed/departed entries. It is not 22 unique vessels, live occupancy, available capacity or predicted waiting. Anchorage has a separate date-only scope: 3 READY and 13 NOT READY rows. Publication time is unknown; interpreting the working section's 06:00 clock as IST is an explicit assumption.

The unchanged policy qualifies the report at collection and capture. Its six-hour successful-check bound expires independently of the observation-age bounds. A later reader must inspect current eligibility; this recording is not a perpetual freshness claim. The October 30 original remains retained and aged. Source metadata and bounded aggregate facts are shown; the full authority PDF is privately retained and is not redistributed in the demo.

The main journey explicitly selects fictional S16 weather, passage, cargo and handling assumptions, declares WORKING_LISTED_ROWS ≥ 20 for the owned INPRT call, then acknowledges the exact current official context in the existing editor. This creates an unapproved linked successor. Company reviews and approves that successor; a real restart of the dedicated QA backend retains it; Port inspects the frozen source binding, reviews and issues; Vessel acknowledges and accepts; Port records a labelled simulated outcome. The report count contributes no delay, fuel or cost coefficient. The same visitor world is used throughout this role chain.

S06 computes a strategic reroute using the existing engine and geometry. S07 genuinely refuses a diversion after the commitment point. **The strategic reroute is not connected to the bounded port-approach advisory chain in this milestone.** It is not approved navigation. S10/S12/S17 demonstrate speed, permitted departure holding and a hard cargo cutoff; S03 uses a visibly labelled software revision; S25 refuses an unsupported hourly horizon. Mobile Layers/Timeline and the original Admin workspace complete the tour.

Presets do not become real source observations or independent learning targets. Weather learning remains collecting; both rejected candidates remain rejected. Complete costs, measured savings, berth/cargo reservations, actual execution, certified safety, unauthorized CCTV and adopted corrections are unavailable. Visitor sessions retain the existing 12-hour TTL; restart recovery within a valid session is not an unlimited session-lifetime guarantee.

## Reproduce the isolated local app

Use the repository's existing Python/backend and frontend dependencies. The examples assume Python, Node and PowerShell 7 are on PATH. Do not load production environment files. If an existing dependency directory is needed on this checkout, put that directory and the repository root in `PYTHONPATH` locally; do not commit machine-specific paths.

From the repository root, create the dedicated backend launcher:

```powershell
$taskRoot=(Get-Location).Path
$taskWork=Join-Path $taskRoot 'work/current-source-demo'
New-Item -ItemType Directory -Path $taskWork -Force | Out-Null
@'
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$taskState=Join-Path $taskRoot 'work/current-source-demo/state'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PORTWATCH_STATE_DIR=$taskState
$env:PORTWATCH_PUBLIC_FEEDBACK_DB=Join-Path $taskState 'public-feedback.sqlite3'
$env:PORTWATCH_CURRENT_ENVIRONMENT_DIR=Join-Path $taskState 'current_environment'
$env:PORTWATCH_WEATHER_FEEDBACK_DB=Join-Path $taskState 'public-weather.sqlite3'
$env:PORTWATCH_WEATHER_FEEDBACK_REPORT=Join-Path $taskState 'public-weather.json'
$env:PORTWATCH_LICENCE_MODE='DEMO'
$env:PORTWATCH_IDENTITY_MODE='verified'
$env:PORTWATCH_FRESHNESS_SCHEDULER='0'
$env:PORTWATCH_PUBLIC_PORT_AUTOREFRESH='0'
$env:PORTWATCH_WEATHER_RECONCILIATION='0'
$env:PORTWATCH_INTELLIGENCE_RECONCILIATION='0'
$env:PORTWATCH_VESSELFINDER_ENABLED='0'
$env:PORTWATCH_PUBLIC_RESEARCH_DIR=Join-Path $taskRoot 'data/research_release'
$env:PORTWATCH_EXPERIMENT_DIR=Join-Path $taskRoot 'data/research_release/capabilities'
Set-Location -LiteralPath $taskRoot
python -u (Join-Path $taskRoot 'scripts/local_demo_backend.py')
'@ | Set-Content -LiteralPath (Join-Path $taskWork 'run_backend.ps1') -Encoding utf8
pwsh -NoProfile -File scripts/restart_local_demo_backend.ps1
```

The restart helper checks the exact bootstrap and parent launcher before stopping port 8817. It refuses unrelated listeners. Its bootstrap opts only the QA process out of Windows background execution throttling; it does not change a machine power plan. All schedulers above are disabled only for this isolated QA instance. The ordinary backend collector lifecycle and archived research protocols are unchanged.

Prepare a separate frontend build without touching a running checkout's output:

```powershell
@'
from pathlib import Path
import shutil, subprocess
root=Path.cwd()
source=root/'india-portwatch-terminal'
target=root/'work/current-source-demo/frontend-build'
shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns(
    'node_modules','.output','.tanstack','.vercel','.playwright','playwright-report',
    'test-results','.env','.env.*','.git','dist'))
if not (target/'node_modules').exists():
    subprocess.run(['pwsh','-NoProfile','-Command',
        'New-Item','-ItemType','Junction','-Path',str(target/'node_modules'),
        '-Target',str(source/'node_modules')],check=True)
'@ | python -
$env:NITRO_PRESET='node-server'
$env:VITE_PORTWATCH_API_BASE='http://127.0.0.1:8817/api'
$env:VITE_PORTWATCH_AUTH_MODE='production'
Push-Location -LiteralPath 'work/current-source-demo/frontend-build'
node node_modules/typescript/bin/tsc --noEmit
if($LASTEXITCODE -ne 0){throw 'Type check failed'}
node node_modules/vite/bin/vite.js build
if($LASTEXITCODE -ne 0){throw 'Build failed'}
$env:HOST='127.0.0.1'
$env:PORT='4218'
node .output/server/index.mjs
Pop-Location
```

Keep that preview process running. Stop only its owned process before rebuilding into the same output directory. Open `http://127.0.0.1:4218/login`, choose **Company demo** normally and explicitly refresh the fixed official source family through Global intelligence if the new QA archive is empty. A source GET does not collect or fabricate data. If the issuer has no qualified current product, retain the refusal; do not backdate, widen policy or substitute a fixture in the real-source scene.

## Record and export

In another terminal at the repository root:

```powershell
# Use an already available Playwright browser cache when necessary:
# $env:PLAYWRIGHT_BROWSERS_PATH='<local browser cache>'
$env:PWSH=(Get-Command pwsh).Source
node scripts/record_current_source_demo.mjs --restart-backend
# Without video, for validation only:
node scripts/record_current_source_demo.mjs --quick --restart-backend
# Optional separate, explicitly labelled cargo arithmetic take:
node scripts/record_cargo_detail.mjs
```

The recorder enters through the normal verified demo login. It does not inject authentication storage, mock responses, overwrite application numbers or force clicks. Its only overlay is a visible pointer. It records actual receipt/query times, exact decisions/options/evidence, workflow events and restart readiness. On this host a process-only QoS adjustment was also applied to the owned capture subtree; no other application or global power setting was changed. Failed takes remain labelled failed and are not the final deliverable.

Review successful takes' manifests and actual frames, then prepare chronological `sourceStart`/`sourceEnd` intervals within each take. Retain the supported results, rejection and all human workflow stages. Active actions remain at original speed. The final edit removes idle/loading time, inserts the explicitly separate cargo example, holds actual final frames briefly for reading and enlarges the complete 390×844 mobile viewport after removing recorder padding. Clocks pause during labelled reading holds; no application value/result is invented. Each clip names its original scene ID, optional `sourceTake`, optional bounded `readingHoldSeconds` and caption text. The export validates chronological coverage in each take, required scenes and a six-to-eight-minute duration.

```powershell
python scripts/export_current_source_demo.py work/current-source-demo/video/<successful-take> `
  --edit-plan work/current-source-demo/video/<successful-take>/edit-plan.json `
  --ffmpeg work/current-source-demo/tools/ffmpeg-n8.1-latest-win64-gpl-shared-8.1/bin/ffmpeg.exe
```

The initial installed Playwright encoder supported VP8 but lacked H.264 and scene concatenation. A portable FFmpeg n8.1 archive was subsequently downloaded into ignored local work storage, verified against GitHub's asset SHA-256 `29f1f119545c5998b52a1e1a23c08fbf1bd4f851e380a718c5b71386125f259a`, and used for the preferred H.264 export. It was not installed globally or added to PATH. An installed FFmpeg with equivalent H.264/concat support can be supplied instead. Without editing, the exporter preserves the actual original WebM; a failed take cannot be exported as a finished demonstration.

## Validation evidence

- Consolidated backend run: **269 passed**, `work/current-source-demo/final-tests.txt`. This includes clock audits, parser/original/revision safety, source-quality lifecycle, fleet triage, passage/cargo/finance, auth, isolation and restart recovery. Later focused runs overlap that suite; their totals are not independent samples.
- Focused source/API checks: 13 passed; strict parser/original/WAL/refusal checks: 10 passed; scenario and consumed-binding lifecycle checks: 3 passed; other-port fixture-labelling guard: 1 passed. These are software tests, not resolved operational targets.
- Type-checked production build: `build-binding.txt`; scoped lint: `lint-binding.txt`, with no new errors. Existing MapPanelAccess mixed export warning remains.
- Browser validation: `additional-browser-validation.json` passes exact decision/option/evidence deep-link reopening, reload recovery and other-visitor 404 refusal. At both 360 and 390 pixels, Layers and Timeline remain operable with 24 px root text and no horizontal page overflow.
- The separate current-source-bound browser run passes the full real-report binding → Company approval → actual backend restart → Port source inspection/review/issue → Vessel acknowledgement/acceptance → simulated outcome. Its manifest and screenshots are in `video/validation`; the filmed journey has its own exact references in the final manifest.
- Eight protected role/twin files still match `e906f6a` after normalizing CRLF. Both historical October 26 hosting-package hashes are unchanged (`preservation.json`). No model artifact was changed.

## Final media and playback QA

The main successful take is `video/2026-11-01T08-54-20.547Z`, captured November 1 at **14:24 IST** (`08:54:20.588Z`), source commit `7b6dce9a84c5f8eb066eb2b9828fdcfac8aa87b8`. Its actual unedited WebM duration is 420.88 s; all role transitions and the actual backend restart pass with no recorded runtime errors. Backend readiness was regained at capture second 335.1, following Company approval at second 319.2. The official source scene's query was `08:54:46.386170Z`; CURRENT_ELIGIBLE is a capture-time statement.

The separate cargo-detail take is `video/2026-11-01T09-05-33.928Z-cargo-detail`, captured at **14:35 IST**, source commit `6646f18ba25956eeaf000cf660e09e334ca409f2`. Changes between these capture commits affect recording/export scripts only; the application build is identical. Both takes enter through normal Company demo login. The cargo insert retains a different fictional call and clock; the main Company → Port → Vessel journey remains within its original single visitor world.

Measured final media: **445.28 s (7:25), 1920×1080, H.264, yuv420p, 25 fps, 11,132 video frames, no audio**. The cut plan totals 445.25 s; the 0.03 s difference is frame quantization. Chromium plays the file, decodes frames, loads **43 English caption cues**, and successfully seeks to 6, 30, 110, 253, 340, 360, 418 and 441 seconds. Evidence: `video/final-playback-validation.json` and `probe-final.txt`. HTTP byte-range validation returns 206 and the requested 100 bytes. The local player's captions use a smaller readable size to preserve the underlying evidence view.

Actual decoded/video-player samples were visually reviewed at the beginning, official-source scene, computed route, cargo arithmetic, frozen Port context, accepted Vessel advisory, mobile Layers and final Admin workspace. The source, selected comparison, rejection, labels and reading holds match their manifest. No black-map export, sensitive data, hidden rejection or invented result was accepted. Mobile removes only recorder padding around the complete viewport. The source attribution and simulation limitations remain visible.

| Final chapter | What is shown |
| --- | --- |
| 00:18 | Real official source, clocks, aggregates and operator criterion |
| 00:57 | Existing fleet queue and separate source responsibility |
| 01:29 / 02:05 | Computed reroute / commitment-point refusal |
| 02:30 / 03:05 / 03:30 | Speed / permitted departure / rejected cargo connection |
| 04:00 | Separate cargo arithmetic, cutoff and signed slack |
| 04:28 | Main official-context binding and linked successor |
| 05:05 / 05:17 | Company approval / actual backend restart |
| 05:33 / 05:46 / 05:54 | Port evidence inspection / issue / Vessel acceptance |
| 06:04 | Labelled simulated outcome |
| 06:13 / 06:39 | Software source revision / unknown hourly horizon |
| 06:55 / 07:01 / 07:17 | Mobile Layers / Timeline / original Admin |

Main approved source-bound comparison: `dec-arrival-a73e15f5b42fd86e1d08`; predecessor `dec-arrival-9246a248208ec9229279`; selected option `passage-slow_steam-0670d6c74ff657f497a5`; evidence `985a773efb79b614923242561979a7f1249dea7a0a9cb3bc35b3f8b2490bf04e`; issued/accepted advisory `ADV-INPRT-787AF27919`. The report binding freezes the original hash above, WORKING_LISTED_ROWS 22 and operator threshold 20. The main manifest records each advisory transition and actual restart readiness.

Separate cargo-detail comparison: `dec-arrival-9e3b3911b50dfc6af5fb`; evidence `37c1ff1e8a09fb78247dc1ef043b789fa013f05bf77511441d831dd980a56ebd`. For that call, handling is `1 + 1.5 + 0 + 1.090909 = 3.590909 h`; conditional completion is November 2 17:35:27Z against its declared 19:00Z cutoff, giving `+1.409091 h` slack. These timestamps belong to the insert, not the main advisory's schedule. No reservation or actual cargo outcome is asserted.

Final SHA-256 values:

```text
MP4       a1efdddb5c4270e8eab1303b59d7b103130f8258faa938c52ce82a6b8fc804ea
captions  1db6d70dcdcabd67751b1a8c98bec4a87464fad451fc99cf9f49f523e493f177
poster    410269ca13bc852ea3df5909b2494d09dade10fe035c23a2b639d3a493e2d65a
manifest  a6ed8f5dcf172a01bb80d3fbd426b7e59e1eb3e456c2233301377360bb3b867d
```

The actual final export command was:

```powershell
python scripts/export_current_source_demo.py work/current-source-demo/video/2026-11-01T08-54-20.547Z `
  --edit-plan work/current-source-demo/video/2026-11-01T08-54-20.547Z/edit-plan.json `
  --ffmpeg work/current-source-demo/tools/ffmpeg-n8.1-latest-win64-gpl-shared-8.1/bin/ffmpeg.exe
```

Git contains the implementation, tests, catalogue, narration, recording/export/player scripts and this handoff. It contains no media, authority PDF bytes, visitor/session state, portable encoder or unrelated modified CSVs. Final source/documentation commits preserve the recorded application code; no deployment or public upload was performed.
