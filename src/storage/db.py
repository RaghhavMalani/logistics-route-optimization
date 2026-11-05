"""Database persistence (PostgreSQL with SQLite fallback).

Connection resolution order:
  1. explicit `url` argument,
  2. the DATABASE_URL environment variable (e.g. the docker-compose Postgres),
  3. a local SQLite file at outputs/logistics.db  (zero-setup default).

If a Postgres URL is given but the server is unreachable, we log a warning and
fall back to SQLite so a demo never dies on infrastructure.

Tables (created on demand via pandas.to_sql):
    raw_weather, raw_news, raw_port_ops, raw_trade, observed,
    expert_weather, expert_news, expert_port_ops, expert_trade, feature_panel,
    regimes, forecasts, decisions, route_recommendations, benchmark
"""

from __future__ import annotations

from src.utils.settings import get_settings

from typing import Dict, Optional

import pandas as pd

from src.utils.config import OUTPUTS_DIR
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

_DEFAULT_SQLITE = f"sqlite:///{(OUTPUTS_DIR / 'logistics.db').as_posix()}"


def _sqlalchemy():
    try:
        import sqlalchemy
        return sqlalchemy
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("SQLAlchemy not installed. `pip install sqlalchemy` "
                           "(and psycopg2-binary for Postgres).") from exc


def get_engine(url: Optional[str] = None):
    """Return a SQLAlchemy engine, falling back to SQLite if Postgres is down."""
    sa = _sqlalchemy()
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    url = url or get_settings().DATABASE_URL or _DEFAULT_SQLITE

    try:
        engine = sa.create_engine(url, future=True)
        with engine.connect() as conn:                # probe the connection
            conn.execute(sa.text("SELECT 1"))
        log.info("Storage: connected to %s", _safe(url))
        return engine
    except Exception as exc:
        if url.startswith("sqlite"):
            raise
        log.warning("Storage: could not connect to %s (%s); falling back to SQLite.",
                    _safe(url), exc)
        engine = sa.create_engine(_DEFAULT_SQLITE, future=True)
        return engine


def _safe(url: str) -> str:
    """Hide credentials when logging a DB URL."""
    if "@" in url and "//" in url:
        head, tail = url.split("//", 1)
        if "@" in tail:
            return head + "//***@" + tail.split("@", 1)[1]
    return url


def save_df(df: pd.DataFrame, table: str, engine,
            if_exists: str = "replace") -> int:
    if df is None or df.empty:
        log.info("Storage: skip empty table '%s'.", table)
        return 0
    out = df.copy()
    # SQLite/Postgres dislike tz-aware datetimes; strip tz only when present.
    for c in out.columns:
        if pd.api.types.is_datetime64tz_dtype(out[c]):
            out[c] = out[c].dt.tz_localize(None)
    out.to_sql(table, engine, if_exists=if_exists, index=False)
    log.info("Storage: wrote %d rows -> %s", len(out), table)
    return len(out)


def load_df(table: str, engine) -> pd.DataFrame:
    try:
        return pd.read_sql_table(table, engine)
    except Exception:
        try:
            return pd.read_sql(f"SELECT * FROM {table}", engine)
        except Exception as exc:
            log.warning("Storage: could not read '%s' (%s).", table, exc)
            return pd.DataFrame()


def persist_pipeline(engine, *, bundle: Dict[str, pd.DataFrame] | None = None,
                     experts: Dict[str, pd.DataFrame] | None = None,
                     panel: pd.DataFrame | None = None,
                     regimes: pd.DataFrame | None = None,
                     forecast: pd.DataFrame | None = None,
                     decisions: pd.DataFrame | None = None,
                     routes: pd.DataFrame | None = None,
                     benchmark: pd.DataFrame | None = None) -> None:
    """Persist every stage of one pipeline run into the database."""
    mapping = {}
    if bundle:
        mapping.update({
            "raw_weather": bundle.get("weather_raw"),
            "raw_news": bundle.get("news_raw"),
            "raw_port_ops": bundle.get("port_ops_raw"),
            "raw_trade": bundle.get("trade_raw"),
            "observed": bundle.get("observed"),
        })
    if experts:
        mapping.update({
            "expert_weather": experts.get("weather"),
            "expert_news": experts.get("news"),
            "expert_port_ops": experts.get("port_ops"),
            "expert_trade": experts.get("trade"),
        })
    mapping.update({
        "feature_panel": panel, "regimes": regimes, "forecasts": forecast,
        "decisions": decisions, "route_recommendations": routes,
        "benchmark": benchmark,
    })
    for table, df in mapping.items():
        if df is not None:
            save_df(df, table, engine)
