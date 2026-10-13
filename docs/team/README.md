# Team branch starting point

Shared branch: [feat/portwatch-restored-intelligence](https://github.com/RaghhavMalani/logistics-route-optimization/tree/feat/portwatch-restored-intelligence).

This branch starts from main after the older deployment branch was merged. It records the restored application, connected role demos, weather reconciliation, authority-notice workflow, public research/case assets and the teammate briefs. Ananya and Preksha should branch from this remote branch's tip, recording its exact SHA.

- [Ananya's port-twin assignment](D:/LogisticOptimization-_Capstone_168/docs/team/ANANYA_ACCURATE_PORT_TWINS.md).
- [Preksha's UI/data assignment](D:/LogisticOptimization-_Capstone_168/docs/team/PREKSHA_UI_DATA_PRODUCT.md).
- [Ownership, branch commands and feedback plan](D:/LogisticOptimization-_Capstone_168/docs/team/PARALLEL_WORK_AND_FEEDBACK_PLAN.md).

The absolute paths in these working briefs refer to the original workspace. In your clone, open the corresponding files under docs/team.

## What the source snapshot contains

Application source, dependency manifests/lockfile, public port-activity inputs, public PDF fixtures, mapped geographic assets, immutable public case/research releases and the published rejected model artifacts are included. The model artifact/report files under data/research_release/capabilities are copied byte-for-byte from the validated public backend package; their statuses remain REJECTED.

Generated caches, databases, visitor/session/operator state, credentials, local work directories, temporary captures and installed dependencies are excluded. Production evidence remains on its persistent storage. A fresh clone does not inherit its visitor worlds, forecast archive counts or collected observation history.

## Isolated local setup

Use your own clone and local state. Install the Python runtime dependencies from requirements.txt in your own virtual environment. The deep-learning stack is optional and is not needed for the assigned UI or geometry work.

Existing source inputs can generate a development cache:

    python run_award_demo.py --source portwatch --model baseline --offline

This is a development pipeline run. Preserve its source-age and synthetic/degraded labels; it does not reproduce the deployed forecast archive or verify a past forecast.

For a local backend, use port 8000 and a new PORTWATCH_STATE_DIR under your clone's work directory. Set PORTWATCH_LICENCE_MODE=DEMO and PORTWATCH_IDENTITY_MODE=verified. Set PORTWATCH_EXPERIMENT_DIR to the absolute data/research_release/capabilities directory in your clone.

Start with background source collection disabled for UI/geometry development:

    PORTWATCH_FRESHNESS_SCHEDULER=0
    PORTWATCH_PUBLIC_PORT_AUTOREFRESH=0
    PORTWATCH_WEATHER_RECONCILIATION=0

These are environment settings to apply in your shell, not lines to execute as commands. The integration owner owns the live collection configuration. Request-driven public weather checks can still occur through the current-input panels. Never point your development process at production storage.

Run the API from the repository root:

    python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

In india-portwatch-terminal, use Node 24 as specified by the existing CI configuration, then install from the lockfile with npm ci. Configure VITE_PORTWATCH_API_BASE=http://127.0.0.1:8000/api and VITE_PORTWATCH_AUTH_MODE=production in your local, ignored frontend environment file. Run npm run dev.

Use the four one-click role demos. Each visitor has isolated fictional state; demo sessions last 12 hours. Operational accounts and private feeds are not provided by the repository.

## Before opening a PR

Record your shared-base SHA, changed files, source/asset provenance, schema changes and limitations. Include relevant tests, TypeScript/build checks and before/after screenshots. Keep the native four-role journey and existing evidence semantics intact. Follow india-portwatch-terminal/AGENTS.md and preserve published history.

Production deployment and integration stay with the integration owner. These branch instructions do not change the public deployment.
