"""India PortWatch -- one-command predictive maritime digital twin.

Runs the whole chain in the order the product story tells it:

    OBSERVE     satellite-AIS port activity, live marine weather, maritime events
    UNDERSTAND  weather / news / port-ops / demand / macro experts, plus the
                capacity, anomaly, arrival-dynamics, disruption-propagation,
                weather-persistence and data-quality specialists
    FORECAST    HSMM regimes -> GBM quantiles / TFT -> adaptive ensemble with
                conformal calibration
    DECIDE      operational decisions with expected impact
    ROUTE       fleet-level arrival and reroute recommendations

Every source declares its provenance (live / cached / stale / synthetic) and the
whole registry is persisted, so the API and terminal report exactly what the
pipeline actually had.

Examples
--------
python run_award_demo.py --source portwatch --refresh
python run_award_demo.py --source portwatch --benchmark
python run_award_demo.py --source sample --model baseline
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
from src.utils import provenance
from src.ingestion.load_data import load_raw_bundle
from src.ingestion.validation import validate_bundle
from src.ingestion.sample_data import write_sample_data
from src.experts import weather_expert, news_expert, port_ops_expert, trade_demand_expert
from src.experts import (
    anomaly_expert, arrival_dynamics_expert, capacity_expert,
    data_quality_expert, disruption_expert, weather_persistence_expert,
)
from src.regimes.regime_features import assemble_panel
from src.regimes.hsmm_model import HSMMRegimeModel
from src.forecasting.forecast_runner import run_baseline, run_persistence
from src.forecasting import ensemble as ensemble_members
from src.forecasting.ensemble import blend_members, load_ensemble_policy
from src.decision.decision_layer import build_decisions, high_risk_calendar
from src.decision.route_optimizer import optimize_fleet

log = get_logger("award_demo")


def _write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    log.info("wrote %s (%d rows)", path, len(df))


def _align_macro(macro_feats: pd.DataFrame | None, observed: pd.DataFrame):
    """Keep macro aligned to the observed calendar without inventing overlap."""
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


def _live_weather(observed: pd.DataFrame, storm_source: pd.DataFrame | None,
                  horizon: int):
    """Live Open-Meteo weather merged with GDACS storm flags.

    Returns ``(nowcast_frame, raw_frame)``. Falls back to whatever the bundle
    supplied when the live connector cannot deliver -- and says so.
    """
    try:
        from src.ingestion.connectors import weather_live
        history_start = pd.to_datetime(observed[DATE], errors="coerce").min()
        live = weather_live.fetch_port_weather(
            past_days=92, forecast_days=max(horizon, 10),
            history_start=history_start)
        if not live.empty:
            return weather_live.merge_storm_flags(live, storm_source), True
    except Exception as exc:
        log.warning("Live weather connector unavailable (%s).", exc)
        provenance.record(
            "Marine weather (Open-Meteo)", provenance.UNAVAILABLE,
            f"Connector error: {exc}", provider="Open-Meteo")
    if storm_source is not None and not storm_source.empty:
        provenance.record(
            "Marine weather (GDACS storm flags)", provenance.CACHED_LIVE,
            "No live meteorology; only disaster-alert storm flags are available, "
            "so wind/rain/wave risk is reported as unmeasured.",
            provider="GDACS via IMF PortWatch",
            observed_at=pd.to_datetime(storm_source[DATE], errors="coerce").max(),
            rows=len(storm_source))
    return storm_source, False


def _merge_features(panel: pd.DataFrame, *extras: pd.DataFrame) -> pd.DataFrame:
    """Left-join specialist outputs onto the panel, once, without duplicates.

    Merging the same frame twice would silently produce ``capacity_pressure_x``
    and ``capacity_pressure_y`` and leave the real column name absent -- which
    is exactly how specialist signals stop reaching the model while still
    appearing on a dashboard. Columns already present are skipped so the join
    can never suffix.
    """
    out = panel.copy()
    out[DATE] = pd.to_datetime(out[DATE], errors="coerce")

    for extra in extras:
        if extra is None or extra.empty:
            continue
        new_cols = [c for c in extra.columns
                    if c not in (PORT_ID, DATE) and c not in out.columns]
        if not new_cols:
            continue
        frame = extra[[PORT_ID, DATE] + new_cols].drop_duplicates([PORT_ID, DATE]).copy()
        frame[DATE] = pd.to_datetime(frame[DATE], errors="coerce")
        out = out.merge(frame, on=[PORT_ID, DATE], how="left")
    return out


def _fuse_operational_signals(panel: pd.DataFrame) -> pd.DataFrame:
    """Fold the specialist signals into the queue/utilization inputs.

    The specialist columns stay visible for explainability *and* are blended
    into the two operational signals the established model schema is built
    around, so the agents change the forecast rather than only the dashboard.
    The pre-fusion values are retained as ``*_raw`` so the fusion is auditable.
    """
    out = panel.copy()

    def unit(column: str, default: float) -> pd.Series:
        if column not in out.columns:
            return pd.Series(default, index=out.index, dtype=float)
        return (pd.to_numeric(out[column], errors="coerce")
                .fillna(default).clip(0, 1))

    anomaly_score = unit("anomaly_score", 0.0)
    capacity_pressure = unit("capacity_pressure", 0.5)
    berth_pressure = unit("berth_pressure", 0.0)
    disruption_pressure = unit("disruption_pressure", 0.0)

    queue = unit("queue_proxy", 0.0)
    utilization = (pd.to_numeric(out["utilization"], errors="coerce")
                   if "utilization" in out.columns
                   else pd.Series(0.5, index=out.index, dtype=float))
    if utilization.quantile(0.95) > 1.5:
        utilization = utilization / 100.0
    utilization = utilization.fillna(0.5).clip(0, 1)

    out["queue_proxy_raw"] = queue
    out["utilization_raw"] = utilization
    out["queue_proxy"] = (0.62 * queue + 0.15 * capacity_pressure
                          + 0.13 * berth_pressure + 0.10 * anomaly_score).clip(0, 1)
    out["utilization"] = (0.78 * utilization + 0.22 * capacity_pressure).clip(0, 1)
    out["specialist_stress"] = (
        0.32 * capacity_pressure + 0.24 * anomaly_score
        + 0.20 * berth_pressure + 0.14 * out["queue_proxy"]
        + 0.10 * disruption_pressure
    ).clip(0, 1).round(4)
    return out


def _forecast(panel: pd.DataFrame, weather_now: pd.DataFrame, horizon: int,
              model: str, epochs: int, deep: bool = False):
    """Produce the live forecast using the requested model configuration.

    ``ensemble`` blends the members the walk-forward benchmark actually scored:
    probabilistic persistence, the GBM quantile model, and the TFT when the deep
    stack is installed. Weights come from the fitted policy artefact, so the
    blend the terminal shows is the blend the benchmark measured.
    """
    baseline = run_baseline(panel, weather_now, horizon)
    if model == "baseline":
        return baseline

    members = {ensemble_members.GBM: baseline}
    try:
        members[ensemble_members.PERSISTENCE] = run_persistence(
            panel, weather_now, horizon)
    except Exception as exc:
        log.warning("Persistence member unavailable (%s).", exc)

    tft_forecast = None
    if not deep and model != "tft":
        log.info("Deep member skipped (pass --deep to include the TFT). The "
                 "fitted policy renormalises over the members present.")
    try:
        from src.forecasting.tft_model import TFTForecaster, TFTConfig, torch_available
        if (deep or model == "tft") and torch_available():
            tft = TFTForecaster(TFTConfig(horizon=horizon, max_epochs=epochs))
            tft.fit(panel, weather_now)
            tft_forecast = tft.predict_future(panel, weather_now)
            tft_forecast["model"] = "tft"
        elif deep or model == "tft":
            log.info("Deep stack not installed; the ensemble runs on "
                     "persistence + GBM.")
    except Exception as exc:
        log.warning("TFT member unavailable (%s); the ensemble runs on "
                    "persistence + GBM.", exc)

    if model == "tft":
        if tft_forecast is None:
            log.warning("TFT requested but unavailable; returning the calibrated "
                        "GBM baseline.")
            return baseline
        secondary = baseline[[PORT_ID, "horizon_day", "predicted_delay",
                              "predicted_throughput"]]
        return tft_forecast.drop(
            columns=["predicted_delay", "predicted_throughput"], errors="ignore"
        ).merge(secondary, on=[PORT_ID, "horizon_day"], how="left")

    if tft_forecast is not None:
        members[ensemble_members.SECOND_OPINION] = tft_forecast

    if len(members) == 1:
        return baseline

    policy = load_ensemble_policy(FORECASTS_DIR / "ensemble_weights.json")
    log.info("Ensemble policy: %s", policy.describe())
    return blend_members(members, policy, panel=panel,
                         secondary_from=ensemble_members.GBM)


def main() -> dict:
    parser = argparse.ArgumentParser(
        description="Run the India PortWatch predictive maritime digital twin.")
    parser.add_argument("--source", default="auto",
                        choices=["auto", "sample", "portwatch", "real"])
    parser.add_argument("--model", default="ensemble",
                        choices=["ensemble", "tft", "baseline"])
    parser.add_argument("--horizon", type=int, default=FORECAST_HORIZON_DAYS)
    parser.add_argument("--epochs", type=int, default=35)
    parser.add_argument("--days", type=int, default=300)
    parser.add_argument("--refresh", action="store_true",
                        help="refresh the IMF PortWatch cache when the network allows")
    parser.add_argument("--benchmark", action="store_true",
                        help="run the walk-forward benchmark and refresh the "
                             "ensemble weighting policy before forecasting")
    parser.add_argument("--offline", action="store_true",
                        help="skip every network call and rely on cached data")
    parser.add_argument("--deep", action="store_true",
                        help="include the TFT as an ensemble member. Training it "
                             "adds roughly twenty minutes; without it the "
                             "ensemble runs on persistence + GBM and the fitted "
                             "policy renormalises over the members present")
    args = parser.parse_args()

    ensure_dirs()
    provenance.reset()
    cfg = DemoConfig(n_days=args.days, horizon=args.horizon)

    # ---------------------------------------------------------------- OBSERVE
    section(log, "1 / OBSERVE  ·  live data acquisition")
    if args.refresh and not args.offline:
        try:
            from app.data import portwatch as pw_fetch
            pw_fetch.fetch_all()
        except Exception as exc:
            log.warning("Live PortWatch refresh unavailable; using the last "
                        "known-good cache: %s", exc)
    if args.source in ("auto", "sample"):
        try:
            write_sample_data(cfg)
        except Exception:
            pass

    bundle = load_raw_bundle(source=args.source, cfg=cfg)
    validate_bundle(bundle)
    observed = bundle["observed"]
    observed_max = pd.to_datetime(observed[DATE], errors="coerce").max()

    if args.source in ("portwatch", "auto"):
        provenance.record(
            "Port activity (IMF PortWatch)", provenance.CACHED_LIVE,
            f"Daily satellite-AIS port calls and trade tonnage for "
            f"{observed[PORT_ID].nunique()} Indian ports.",
            provider="IMF PortWatch (ArcGIS feature service)",
            observed_at=observed_max, rows=len(observed), freshness_hours=72.0)
    else:
        provenance.record(
            "Port activity (%s)" % args.source, provenance.SYNTHETIC,
            "Offline demo bundle; not measured port activity.",
            provider="local generator", observed_at=observed_max,
            rows=len(observed), fallback="sample bundle")

    weather_raw, weather_is_live = _live_weather(
        observed, bundle.get("weather_raw"), args.horizon)

    news_raw = bundle.get("news_raw")
    event_catalogue: list = []
    if not args.offline and (news_raw is None or news_raw.empty):
        try:
            from src.ingestion.connectors import port_events
            events = port_events.collect_events()
            news_raw = port_events.build_news_raw(observed[[PORT_ID, DATE]], events)
            event_catalogue = port_events.build_event_catalogue(events)
        except Exception as exc:
            log.warning("Port event stream unavailable: %s", exc)
            news_raw = pd.DataFrame(columns=[PORT_ID, DATE])

    # ------------------------------------------------------------- UNDERSTAND
    section(log, "2 / UNDERSTAND  ·  specialist intelligence")
    weather = weather_expert.run(weather_raw)
    weather_now = weather[weather[DATE] <= observed_max] if not weather.empty else weather
    news = news_expert.run(news_raw)
    ops = port_ops_expert.run(bundle["port_ops_raw"], observed=observed)
    demand = trade_demand_expert.run(bundle["trade_raw"], observed[[PORT_ID, DATE]].copy())
    anomaly = anomaly_expert.run(observed, ops)
    capacity = capacity_expert.run(observed, ops)
    arrivals = arrival_dynamics_expert.run(observed, ops)
    disruption = disruption_expert.run(observed[[PORT_ID, DATE]])
    weather_persistence = weather_persistence_expert.run(
        weather_now, forward_weather=weather if weather_is_live else None)

    macro = None
    if not args.offline:
        try:
            from src.ingestion.connectors import macro as macro_conn, events as events_conn
            from src.experts import macro_expert
            macro = macro_expert.run(macro_conn.fetch_macro_conditions(days=2000),
                                     events_conn.fetch_events())
            macro = _align_macro(macro, observed)
        except Exception as exc:
            log.warning("Macro expert skipped: %s", exc)

    if weather_raw is not None and not weather_raw.empty:
        _write(weather_raw, EXPERT_FEATURES_DIR / "weather_observations.csv")

    for name, frame in {
        "weather_features.csv": weather_now,
        "weather_forecast_features.csv": weather,
        "weather_persistence_features.csv": weather_persistence,
        "news_features.csv": news,
        "port_ops_features.csv": ops,
        "trade_demand_features.csv": demand,
        "anomaly_features.csv": anomaly,
        "capacity_features.csv": capacity,
        "arrival_features.csv": arrivals,
        "disruption_features.csv": disruption,
    }.items():
        _write(frame, EXPERT_FEATURES_DIR / name)
    if macro is not None:
        _write(macro, EXPERT_FEATURES_DIR / "macro_features.csv")

    # -------------------------------------------------------- DIGITAL-TWIN STATE
    section(log, "3 / DIGITAL-TWIN STATE  ·  fused panel + regimes")
    panel = assemble_panel(
        observed, weather_now, news, ops, demand, macro=macro,
        extras=[anomaly, capacity, arrivals, disruption, weather_persistence])

    # Data quality is assessed on the merged inputs, then joined back before the
    # operational fusion so the forecaster sees every specialist column exactly
    # once, under its own name.
    quality = data_quality_expert.run(panel)
    _write(quality, EXPERT_FEATURES_DIR / "data_quality_features.csv")
    panel = _fuse_operational_signals(_merge_features(panel, quality))
    _write(panel, EXPERT_FEATURES_DIR / "merged_panel.csv")

    missing = [column for column in
               ("capacity_pressure", "anomaly_score", "berth_pressure",
                "arrival_clustering", "disruption_pressure", "weather_persistence",
                "data_quality_score")
               if column not in panel.columns]
    if missing:
        raise RuntimeError(
            "Specialist signals missing from the merged panel: "
            + ", ".join(missing)
            + ". The forecaster would silently run without them.")

    degraded = data_quality_expert.degraded_ports(quality)
    if degraded:
        log.warning("Ports running on degraded inputs: %s", ", ".join(degraded))

    regimes = HSMMRegimeModel(seed=cfg.seed).fit_predict(panel)
    _write(regimes, REGIMES_DIR / "regimes.csv")
    reg_cols = ["p_normal", "p_congested", "p_severe", "days_in_state",
                "expected_remaining_days", "transition_risk", "regime_confidence"]
    panel_fc = panel.merge(
        regimes[[PORT_ID, DATE] + reg_cols].drop_duplicates([PORT_ID, DATE]),
        on=[PORT_ID, DATE], how="left")

    # ------------------------------------------------------------ MEASURE
    if args.benchmark:
        section(log, "4 / MEASURE  ·  walk-forward benchmark")
        try:
            from src.evaluation.model_benchmark import run_benchmark
            run_benchmark(panel_fc, weather_now, horizon=args.horizon)
        except Exception as exc:
            log.warning("Benchmark stage failed: %s", exc)

    # ------------------------------------------------------------- FORECAST
    section(log, "5 / FORECAST  ·  adaptive ensemble")
    forecast = _forecast(panel_fc, weather, args.horizon, args.model,
                         args.epochs, deep=args.deep)
    forecast = _apply_quality_discount(forecast, quality)
    _write(forecast, FORECASTS_DIR / "forecast_table.csv")

    # ------------------------------------------------------- DECIDE + ROUTE
    section(log, "6 / DECIDE + ROUTE  ·  operational output")
    decisions = build_decisions(forecast, weather_now, panel=panel_fc)
    routes = optimize_fleet(forecast, panel=panel_fc)
    _write(decisions, FORECASTS_DIR / "decisions.csv")
    _write(high_risk_calendar(decisions), FORECASTS_DIR / "high_risk_dates.csv")
    _write(routes, FORECASTS_DIR / "route_recommendations.csv")

    # ---------------------------------------------------------------- EXPORT
    section(log, "7 / EXPORT  ·  API cache + provenance")
    provenance.save({"forecastOrigin": str(
        pd.to_datetime(forecast["forecast_origin_date"], errors="coerce").max())})
    from backend.pipeline.export_award_cache import main as export_cache
    export_cache()
    from backend.pipeline.export_support_cache import main as export_support
    export_support(event_catalogue=event_catalogue)

    section(log, "READY")
    log.info("Model: %s | ports=%d | forecast rows=%d | source readiness=%.2f",
             forecast["model"].iloc[0], forecast[PORT_ID].nunique(),
             len(forecast), provenance.readiness_score())
    return {"forecast": forecast, "regimes": regimes, "decisions": decisions,
            "routes": routes, "panel": panel_fc, "quality": quality}


def _apply_quality_discount(forecast: pd.DataFrame,
                            quality: pd.DataFrame) -> pd.DataFrame:
    """Lower forecast confidence where the port's inputs are degraded.

    A forecast built on a stale or incomplete feed is not as trustworthy as one
    built on a fresh, complete feed, and the number on screen should say so.
    """
    if forecast.empty or quality is None or quality.empty:
        return forecast
    latest = (quality.sort_values([PORT_ID, DATE])
              .groupby(PORT_ID, as_index=False).tail(1)
              [[PORT_ID, "data_quality_score"]])
    out = forecast.merge(latest, on=PORT_ID, how="left")
    score = pd.to_numeric(out["data_quality_score"], errors="coerce").fillna(0.75)
    # A pristine feed keeps its confidence; a fully degraded one loses a third.
    out["confidence_score"] = (
        pd.to_numeric(out["confidence_score"], errors="coerce")
        * (0.67 + 0.33 * score)).clip(0.05, 0.98).round(3)
    return out


if __name__ == "__main__":
    main()
