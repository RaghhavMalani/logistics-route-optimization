# India PortWatch -- pipeline + API image.
#
# One image serves three roles, selected by the command:
#   pipeline   python run_award_demo.py --source portwatch
#   api        the default command: uvicorn on $PORT (8000 unless the host sets it)
#   refresher  python scripts/live_refresh.py --interval-minutes 30
#
# The API listens on the PORT the host hands it. Vercel, Cloud Run, Railway
# and Fly all route to $PORT and give up on a container that listens on a
# hardcoded 8000; docker compose sets nothing and gets the default.
#
# Set PORTWATCH_LICENCE_MODE in the host's environment. Without it the API
# runs in COMMERCIAL, the most restrictive mode, and says so on /api/health;
# the demo needs DEMO.
#
# The deep-learning stack is not installed here: the adaptive ensemble runs on
# probabilistic persistence plus the GBM quantile model without it, which keeps
# the image small enough to deploy anywhere. Add requirements-tft.txt if you
# want the TFT member in production.

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build tooling is needed for hmmlearn's wheels on slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY backend ./backend
COPY app ./app
COPY scripts ./scripts
COPY data ./data
COPY tests ./tests
COPY run_award_demo.py run_demo.py ./

# The API reads artefacts from these directories; create them so a container
# started before the first pipeline run reports "not ready" instead of crashing.
#
# Three kinds of state, three places:
#   /app/state       MUST PERSIST  the decision ledger, the advisory register,
#                                  the operator's cost assumptions. Mount a
#                                  persistent volume here; PORTWATCH_STATE_DIR
#                                  points the stores at it.
#   /app/data/cache  CACHE         provider fetches (event register, marine
#                                  grid, port forecasts). Rebuilt by the
#                                  freshness coordinator; a volume keeps a
#                                  restart from refetching, nothing more.
#   /app/outputs     REBUILDABLE   pipeline artefacts. A volume or a pipeline run.
RUN mkdir -p outputs/expert_features outputs/regimes outputs/forecasts \
             outputs/analytics data/cache state
VOLUME ["/app/state", "/app/data/cache", "/app/outputs"]

ENV PORT=8000 \
    PORTWATCH_STATE_DIR=/app/state
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:${PORT}/api/health || exit 1

# One worker, always. The world, the freshness coordinator, the branch
# registry and the decision engine's memory are per process; a second worker
# would hold a second world and answer differently. Scale by giving this
# process more CPU, not by adding workers.
CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
