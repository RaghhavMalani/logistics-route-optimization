# India PortWatch -- pipeline + API image.
#
# One image serves three roles, selected by the command:
#   pipeline   python run_award_demo.py --source portwatch
#   api        uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
#   refresher  python scripts/live_refresh.py --interval-minutes 30
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
RUN mkdir -p outputs/expert_features outputs/regimes outputs/forecasts \
             outputs/analytics data/cache

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
