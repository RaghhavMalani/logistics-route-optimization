"""One-command showcase pipeline for the India PortWatch digital twin.

This runner keeps the original research pipeline intact while adding two
specialist agents (capacity + anomaly), stress fusion, an adaptive TFT/GBM
ensemble, real HSMM outputs, decisions, route recommendations, and API caches.

Examples
--------
python run_award_demo.py --source portwatch --refresh
python run_award_demo.py --source sample --model ensemble
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.utils.config import (
    DATE, PORT_ID, EXPERT_FEATURES_DIR, FORECASTS_DIR, REGIMES_DIR,
    FORECAST_HORIZON_DAYS, DemoConfig, ensure_dirs,
)
from src.utils.logging_utils import get_logger, section
from src.ingestion.load_data import load_raw_bundle
from src.ingestion.validation import validate_bundle
from src.ingestion.sample_data import write_sample_data
from src.experts import weather_expert, news_expert, port_ops_expert, trade_demand_expert
from src.experts import anomaly_expert, capacity_expert
from src.regimes.regime_features import assemble_panel
from src.regimes.hsmm_model import HSMMRegimeModel
from src.forecasting.forecast_runner import run_baseline
from src.forecasting.ensemble import blend_forecasts, weights_from_benchmark
from src.decision.decision_layer import build_decisions, high_risk_calendar
from src.decision.route_optimizer import optimize_fleet

log = get_logger("award_demo")


def _write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    log.info("wrote %s (%d rows)", path, len(df))


def _align_macro(macro_feats: pd.DataFrame | None, observed: pd.DataFrame):
    if macro_feats is None or macro_feats.empty:
        return macro_feats
    mf = macro_feats.copy()
    mf[DATE] = pd.to_datetime(mf[DATE])
    obs_dates = sorted(pd.to_datetime(observed[DATE]).dropna().unique())
    overlap = set(mf[DATE]).intersection(obs_dates)
    if len(overlap) >= max(5, int(0.3 * len(obs_dates))):
        return mf
    mf = mf.sort_values(DATE)
    n = min(len(mf), len(obs_dates))
    mf = mf.tail(n).copy()
    mf[DATE] = list(obs_dates[-n:])
    return mf


def _fuse_specialists(
    panel: pd.DataFrame,
    anomaly: pd.DataFrame,
    capacity: pd.DataFrame,
) -> pd.DataFrame:
    """Fuse specialist signals into existing model features without leakage.

    New columns remain visible for explainability. A small, bounded contribution
    is also injected into queue/utilization so existing HSMM/TFT configurations
    immediately benefit without changing the established model schema.
    """
    out = panel.copy()
    for extra in (anomaly, capacity):
        if extra is not None and not extra.empty:
            cols = [c for c in extra.columns if c not in (PORT_ID, DATE)]
            out = out.merge(
                extra[[PORT_ID, DATE] + cols].drop_duplicates([PORT_ID, DATE]),
                on=[PORT_ID, DATE], how="left",
            )

    anomaly_score = pd.to_numeric(out.get("anomaly_score", 0.0), errors="coerce").fillna(0.0).clip(0, 1)
    capacity_pressure = pd.to_numeric(out.get("capacity_pressure", 0.5), errors="coerce").fillna(0.5).clip(0, 1)

    queue = pd.to_numeric(out.get("queue_proxy", 0.0), errors="coerce").fillna(0.0).clip(0, 1)
    utilization = pd.to_numeric(out.get("utilization", 0.5), errors="coerce").fillna(0.5)
    if utilization.quantile(0.95) > 1.5:
        utilization = utilization / 100.0
    utilization = utilization.clip(0, 1)

    out["queue_proxy_raw"] = queue
    out["utilization_raw"] = utilization
    out["queue_proxy"] = (0.72 * queue + 0.18 * capacity_pressure + 0.10 * anomaly_score).clip(0, 1)
    out["utilization"] = (0.78 * utilization + 0.22 * capacity_pressure).clip(0, 1)
    out["specialist_stress"] = (
        0.45 * capacity_pressure + 0.35 * anomaly_score + 0.20 * out["queue_proxy"]
    ).clip(0, 1).round(4)
    return out


def _forecast(panel: pd.DataFrame, weather_now: pd.DataFrame, horizon: int, model: str, epochs: int):
    baseline = run_baseline(panel, weather_now, horizon)
    if model == "baseline":
        return baseline

    try:
        from src.forecasting.tft_model import TFTForecaster, TFTConfig, torch_available
        if not torch_available():
            log.warning("TFT stack unavailable; using calibrated GBM baseline.")
            return baseline

        tft = TFTForecaster(TFTConfig(horizon=horizon, max_epochs=epochs))
        tft.fit(panel, weather_now)
        tft_fc = tft.predict_future(panel, weather_now)
        tft_fc["model"] = "tft"

        if model == "tft":
            # Preserve complete secondary targets from the baseline.
            secondary = baseline[[PORT_ID, "horizon_day", "predicted_delay", "predicted_throughput"]]
            return tft_fc.drop(columns=["predicted_delay", "predicted_throughput"], errors="ignore").merge(
                secondary, on=[PORT_ID, "horizon_day"], how="left"
            )

        wt, wb = weights_from_benchmark(FORECASTS_DIR / "benchmark_comparison.csv")
        log.info("Adaptive ensemble weights: TFT=%.3f GBM=%.3f", wt, wb)
        return blend_forecasts(tft_fc, baseline, wt, wb)
    except Exception as exc:
        log.warning("Deep/ensemble path failed (%s); using calibrated GBM baseline.", exc)
        return baseline


def main() -> dict:
    parser = argparse.ArgumentParser(description="Run the award-demo PortWatch digital twin.")
    parser.add_argument("--source", default="auto", choices=["auto", "sample", "portwatch", "real"])
    parser.add_argument("--model", default="ensemble", choices=["ensemble", "tft", "baseline"])
    parser.add_argument("--horizon", type=int, default=FORECAST_HORIZON_DAYS)
    parser.add_argument("--epochs", type=int, default=35)
    parser.add_argument("--days", type=int, default=300)
    parser.add_argument("--refresh", action="store_true", help="refresh IMF PortWatch cache when network is available")
    args = parser.parse_args()

    ensure_dirs()
    cfg = DemoConfig(n_days=args.days, horizon=args.horizon)

    section(log, "1 / LIVE DATA")
    if args.refresh:
        try:
            from app.data import portwatch as pw_fetch
            pw_fetch.fetch_all()
        except Exception as exc:
            log.warning("Live PortWatch refresh unavailable; using last good cache: %s", exc)
    if args.source in ("auto", "sample"):
        try:
            write_sample_data(cfg)
        except Exception:
            pass
    bundle = load_raw_bundle(source=args.source, cfg=cfg)
    validate_bundle(bundle)
    observed = bundle["observed"]

    section(log, "2 / SPECIALIST INTELLIGENCE")
    weather = weather_expert.run(bundle["weather_raw"])
    news = news_expert.run(bundle["news_raw"])
    ops = port_ops_expert.run(bundle["port_ops_raw"], observed=observed)
    demand = trade_demand_expert.run(bundle["trade_raw"], observed[[PORT_ID, DATE]].copy())
    anomaly = anomaly_expert.run(observed, ops)
    capacity = capacity_expert.run(observed, ops)

    macro = None
    try:
        from src.ingestion.connectors import macro as macro_conn, events as events_conn
        from src.experts import macro_expert
        macro = macro_expert.run(macro_conn.fetch_macro_conditions(days=2000), events_conn.fetch_events())
        macro = _align_macro(macro, observed)
    except Exception as exc:
        log.warning("Macro expert skipped: %s", exc)

    for name, frame in {
        "weather_features.csv": weather,
        "news_features.csv": news,
        "port_ops_features.csv": ops,
        "trade_demand_features.csv": demand,
        "anomaly_features.csv": anomaly,
        "capacity_features.csv": capacity,
    }.items():
        _write(frame, EXPERT_FEATURES_DIR / name)
    if macro is not None:
        _write(macro, EXPERT_FEATURES_DIR / "macro_features.csv")

    section(log, "3 / DIGITAL-TWIN STATE")
    panel = assemble_panel(observed, weather, news, ops, demand, macro=macro)
    panel = _fuse_specialists(panel, anomaly, capacity)
    _write(panel, EXPERT_FEATURES_DIR / "merged_panel.csv")

    regimes = HSMMRegimeModel(seed=cfg.seed).fit_predict(panel)
    _write(regimes, REGIMES_DIR / "regimes.csv")
    reg_cols = ["p_normal", "p_congested", "p_severe", "days_in_state",
                "expected_remaining_days", "transition_risk", "regime_confidence"]
    panel_fc = panel.merge(
        regimes[[PORT_ID, DATE] + reg_cols].drop_duplicates([PORT_ID, DATE]),
        on=[PORT_ID, DATE], how="left",
    )

    section(log, "4 / ADAPTIVE FORECAST")
    forecast = _forecast(panel_fc, weather, args.horizon, args.model, args.epochs)
    _write(forecast, FORECASTS_DIR / "forecast_table.csv")

    section(log, "5 / ACTION + ROUTING")
    decisions = build_decisions(forecast, weather)
    routes = optimize_fleet(forecast)
    _write(decisions, FORECASTS_DIR / "decisions.csv")
    _write(high_risk_calendar(decisions), FORECASTS_DIR / "high_risk_dates.csv")
    _write(routes, FORECASTS_DIR / "route_recommendations.csv")

    section(log, "6 / API CACHE")
    try:
        from backend.pipeline.export_award_cache import main as export_cache
        export_cache()
    except Exception as exc:
        log.warning("Award cache export skipped: %s", exc)
    try:
        from backend.pipeline.export_support_cache import main as export_support
        export_support()
    except Exception as exc:
        log.warning("Support cache export skipped: %s", exc)

    section(log, "READY")
    log.info("Model: %s | ports=%d | forecast rows=%d", forecast["model"].iloc[0], forecast[PORT_ID].nunique(), len(forecast))
    return {"forecast": forecast, "regimes": regimes, "decisions": decisions, "routes": routes}


if __name__ == "__main__":
    main()
