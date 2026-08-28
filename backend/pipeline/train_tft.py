from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
OUTPUT_DIR = ROOT / "outputs" / "forecasts"
MODEL_DIR = ROOT / "models" / "tft"

FEATURES_CSV = PROCESSED_DIR / "features_daily_hsmm.csv"
FEATURES_PARQUET = PROCESSED_DIR / "features_daily_hsmm.parquet"

TARGET = "congestion_index"
QUANTILES = [0.1, 0.5, 0.9]


def load_features() -> pd.DataFrame:
    if FEATURES_PARQUET.exists():
        df = pd.read_parquet(FEATURES_PARQUET)
    elif FEATURES_CSV.exists():
        df = pd.read_csv(FEATURES_CSV)
    else:
        raise FileNotFoundError(
            "Could not find data/processed/features_daily_hsmm.parquet or .csv. Run add_hsmm_regimes.py first. "
            "Run backend/pipeline/build_features.py first."
        )

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).copy()
    df["port_id"] = df["port_id"].astype(str)
    df["port_code"] = df["port_code"].astype(str)

    df = df.sort_values(["port_id", "date"]).reset_index(drop=True)

    # Recalculate time_idx so every port has a clean sequence index.
    df["time_idx"] = df.groupby("port_id").cumcount().astype(int)

    return df


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    d = pd.to_datetime(df["date"])

    df["year"] = d.dt.year.astype(int)
    df["month"] = d.dt.month.astype(int)
    df["day_of_week"] = d.dt.dayofweek.astype(int)
    df["day_of_month"] = d.dt.day.astype(int)
    df["is_monsoon"] = d.dt.month.isin([6, 7, 8, 9]).astype(int)

    return df


def clean_model_columns(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    df = df.copy()

    for col in columns:
        if col not in df.columns:
            continue

        df[col] = pd.to_numeric(df[col], errors="coerce")
        df[col] = df[col].replace([np.inf, -np.inf], np.nan)

        if df[col].isna().any():
            median = df[col].median()
            if pd.isna(median):
                median = 0.0
            df[col] = df[col].fillna(median)

    bad = df[columns].isna().sum()
    bad = bad[bad > 0]

    if not bad.empty:
        raise ValueError(f"NaNs remain in TFT columns:\n{bad}")

    for col in columns:
        if np.isinf(pd.to_numeric(df[col], errors="coerce")).any():
            raise ValueError(f"Infinite values found in column: {col}")

    return df


def severity_from_congestion(value: float, q90: float) -> str:
    if value >= 70 or q90 >= 80:
        return "High"
    if value >= 45 or q90 >= 60:
        return "Medium"
    return "Low"


def prepare_tft_panel(df: pd.DataFrame) -> tuple[pd.DataFrame, List[str], List[str]]:
    df = add_calendar_features(df)

    known_reals = [
        "time_idx",
        "month",
        "day_of_week",
        "day_of_month",
        "is_monsoon",
    ]

    # These are observed/context variables. For future inference, we will carry
    # them forward from the latest known port state.
    unknown_candidates = [
        TARGET,
        "delay_hours",
        "throughput_proxy",
        "wind_risk",
        "rain_risk",
        "wave_risk",
        "storm_risk",
        "weather_confidence",
        "news_sentiment_score",
        "news_rolling_risk",
        "demand_pressure",
        "trade_connectivity",
        "trade_trend",
        "p_normal",
        "p_congested",
        "p_severe",
        "days_in_state",
        "expected_remaining_days",
        "transition_risk",
        "regime_confidence",
        "regime_code",
    ]

    unknown_reals = [c for c in unknown_candidates if c in df.columns]

    required = ["time_idx", TARGET] + known_reals + unknown_reals
    required = list(dict.fromkeys(required))

    df = clean_model_columns(df, required)

    return df, known_reals, unknown_reals


def append_future_rows(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    future_rows = []

    for port_id, g in df.groupby("port_id", sort=False):
        g = g.sort_values("date")
        last = g.iloc[-1].copy()
        last_date = pd.to_datetime(last["date"])
        last_idx = int(last["time_idx"])

        for h in range(1, horizon + 1):
            row = last.copy()
            row["date"] = last_date + pd.Timedelta(days=h)
            row["time_idx"] = last_idx + h

            # Target placeholder. PyTorch Forecasting needs a non-NaN value
            # in the future rows, but the model will predict the decoder values.
            row[TARGET] = last[TARGET]

            future_rows.append(row)

    future = pd.DataFrame(future_rows)
    future = add_calendar_features(future)

    extended = pd.concat([df, future], ignore_index=True)
    extended = extended.sort_values(["port_id", "time_idx"]).reset_index(drop=True)

    return extended


def train_tft(
    df: pd.DataFrame,
    known_reals: List[str],
    unknown_reals: List[str],
    horizon: int,
    encoder_length: int,
    max_epochs: int,
    batch_size: int,
    accelerator: str,
) -> tuple[object, object]:
    import torch
    from pytorch_forecasting import TemporalFusionTransformer, TimeSeriesDataSet
    from pytorch_forecasting.data import GroupNormalizer
    from pytorch_forecasting.metrics import QuantileLoss

    try:
        from lightning.pytorch import Trainer, seed_everything
        from lightning.pytorch.callbacks import EarlyStopping
    except Exception:
        from pytorch_lightning import Trainer, seed_everything
        from pytorch_lightning.callbacks import EarlyStopping

    seed_everything(42, workers=True)

    # Hold out the final horizon days per port for validation-style prediction.
    max_idx_per_port = df.groupby("port_id")["time_idx"].transform("max")
    train_df = df[df["time_idx"] <= max_idx_per_port - horizon].copy()

    if train_df.empty:
        raise ValueError("Training frame is empty. Reduce horizon or check feature data.")

    min_rows = train_df.groupby("port_id").size().min()
    if min_rows < encoder_length + horizon:
        raise ValueError(
            f"Some ports have too little history for encoder={encoder_length}, "
            f"horizon={horizon}. Minimum train rows per port: {min_rows}"
        )

    print(f"Training rows: {len(train_df):,}")
    print(f"Ports: {train_df['port_id'].nunique()}")
    print(f"Encoder length: {encoder_length}")
    print(f"Forecast horizon: {horizon}")
    print(f"Known reals: {known_reals}")
    print(f"Unknown reals: {unknown_reals}")

    training_dataset = TimeSeriesDataSet(
        train_df,
        time_idx="time_idx",
        target=TARGET,
        group_ids=["port_id"],
        max_encoder_length=encoder_length,
        min_encoder_length=max(7, encoder_length // 2),
        max_prediction_length=horizon,
        min_prediction_length=1,
        static_categoricals=["port_id"],
        time_varying_known_reals=known_reals,
        time_varying_unknown_reals=unknown_reals,
        target_normalizer=GroupNormalizer(groups=["port_id"], transformation="softplus"),
        add_relative_time_idx=True,
        add_target_scales=True,
        add_encoder_length=True,
        allow_missing_timesteps=True,
    )

    validation_dataset = TimeSeriesDataSet.from_dataset(
        training_dataset,
        df,
        predict=True,
        stop_randomization=True,
    )

    train_loader = training_dataset.to_dataloader(
        train=True,
        batch_size=batch_size,
        num_workers=0,
    )

    val_loader = validation_dataset.to_dataloader(
        train=False,
        batch_size=batch_size,
        num_workers=0,
    )

    model = TemporalFusionTransformer.from_dataset(
        training_dataset,
        learning_rate=0.003,
        hidden_size=32,
        attention_head_size=2,
        dropout=0.15,
        hidden_continuous_size=16,
        loss=QuantileLoss(QUANTILES),
        log_interval=0,
        optimizer="adam",
    )

    early_stop = EarlyStopping(
        monitor="val_loss",
        patience=4,
        mode="min",
    )

    trainer = Trainer(
        max_epochs=max_epochs,
        accelerator=accelerator,
        gradient_clip_val=0.1,
        callbacks=[early_stop],
        enable_checkpointing=False,
        logger=False,
        enable_progress_bar=True,
        enable_model_summary=False,
    )

    print("Training TFT...")
    trainer.fit(model, train_dataloaders=train_loader, val_dataloaders=val_loader)
    print("TFT training complete.")

    return model, training_dataset


def forecast_future(
    model,
    training_dataset,
    df: pd.DataFrame,
    known_reals: List[str],
    unknown_reals: List[str],
    horizon: int,
    batch_size: int,
) -> pd.DataFrame:
    from pytorch_forecasting import TimeSeriesDataSet

    extended = append_future_rows(df, horizon)
    extended = clean_model_columns(
        extended,
        list(dict.fromkeys(["time_idx", TARGET] + known_reals + unknown_reals)),
    )

    prediction_dataset = TimeSeriesDataSet.from_dataset(
        training_dataset,
        extended,
        predict=True,
        stop_randomization=True,
    )

    loader = prediction_dataset.to_dataloader(
        train=False,
        batch_size=batch_size,
        num_workers=0,
    )

    raw = model.predict(loader, mode="quantiles", return_index=True)

    quantiles = raw.output if hasattr(raw, "output") else raw[0]
    index = raw.index if hasattr(raw, "index") else raw[1]

    if hasattr(quantiles, "detach"):
        q = quantiles.detach().cpu().numpy()
    else:
        q = np.asarray(quantiles)

    # Shape should be: series x horizon x quantiles.
    if q.ndim == 2:
        q = q[:, :, None]

    q_map = {round(v, 2): i for i, v in enumerate(QUANTILES)}

    latest_port_info = (
        df.sort_values(["port_id", "date"])
        .groupby("port_id", as_index=False)
        .tail(1)
        [["port_id", "port_code", "date"]]
        .rename(columns={"date": "forecast_origin_date"})
    )

    rows = []

    for s in range(q.shape[0]):
        port_id = str(index.iloc[s]["port_id"])
        base_time_idx = int(index.iloc[s]["time_idx"])
        origin_idx = base_time_idx - 1

        port_ext = extended[extended["port_id"] == port_id].copy()
        port_code = str(port_ext["port_code"].iloc[-1])

        origin_row = port_ext[port_ext["time_idx"] == origin_idx]
        if origin_row.empty:
            origin_date = pd.to_datetime(port_ext["date"].max()) - pd.Timedelta(days=horizon)
        else:
            origin_date = pd.to_datetime(origin_row["date"].iloc[0])

        for h in range(q.shape[1]):
            target_idx = base_time_idx + h
            target_row = port_ext[port_ext["time_idx"] == target_idx]

            if target_row.empty:
                target_date = origin_date + pd.Timedelta(days=h + 1)
            else:
                target_date = pd.to_datetime(target_row["date"].iloc[0])

            q10 = float(q[s, h, q_map.get(0.1, 0)])
            q50 = float(q[s, h, q_map.get(0.5, 0)])
            q90 = float(q[s, h, q_map.get(0.9, q.shape[2] - 1)])

            q10, q50, q90 = sorted([q10, q50, q90])

            rows.append(
                {
                    "port_id": port_id,
                    "port_code": port_code,
                    "forecast_origin_date": origin_date,
                    "target_date": target_date,
                    "horizon_day": h + 1,
                    "q10": q10,
                    "q50": q50,
                    "q90": q90,
                    "predicted_congestion": q50,
                    # Simple delay proxy for now. Decision layer/frontend can use this.
                    "predicted_delay": q50 * 2.0,
                    "model": "tft",
                }
            )

    forecast = pd.DataFrame(rows)

    forecast["uncertainty_band"] = forecast["q90"] - forecast["q10"]
    forecast["risk_level"] = [
        severity_from_congestion(v, hi)
        for v, hi in zip(forecast["predicted_congestion"], forecast["q90"])
    ]

    width_term = 1.0 - (forecast["uncertainty_band"] / 100.0).clip(0, 0.9)
    horizon_term = 1.0 - (forecast["horizon_day"] * 0.03)
    forecast["confidence_score"] = (width_term * horizon_term).clip(0.05, 0.97)

    round_cols = [
        "q10",
        "q50",
        "q90",
        "predicted_congestion",
        "predicted_delay",
        "uncertainty_band",
        "confidence_score",
    ]
    for col in round_cols:
        forecast[col] = pd.to_numeric(forecast[col], errors="coerce").round(3)

    forecast = forecast.sort_values(["port_id", "horizon_day"]).reset_index(drop=True)

    return forecast


def validate_forecast(forecast: pd.DataFrame, horizon: int) -> None:
    required = [
        "port_id",
        "port_code",
        "forecast_origin_date",
        "target_date",
        "horizon_day",
        "q10",
        "q50",
        "q90",
        "predicted_congestion",
        "predicted_delay",
        "risk_level",
        "confidence_score",
        "model",
    ]

    missing = [c for c in required if c not in forecast.columns]
    if missing:
        raise ValueError(f"TFT forecast missing columns: {missing}")

    if forecast[required].isna().any().any():
        print(forecast[required].isna().sum())
        raise ValueError("TFT forecast contains NaNs.")

    if not ((forecast["q10"] <= forecast["q50"]) & (forecast["q50"] <= forecast["q90"])).all():
        raise ValueError("TFT quantiles are not ordered.")

    counts = forecast.groupby("port_id")["horizon_day"].nunique()
    if not (counts == horizon).all():
        print(counts)
        raise ValueError("Some ports do not have all forecast horizon days.")

    if set(forecast["model"].unique()) != {"tft"}:
        raise ValueError(f"Expected only TFT outputs, found: {forecast['model'].unique()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train strict TFT forecast model.")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--horizon", type=int, default=10)
    parser.add_argument("--encoder-length", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument(
        "--accelerator",
        default="cpu",
        help="Use 'cpu' for stable Mac runs, or 'auto' if you want Lightning to choose.",
    )

    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading clean feature table...")
    raw = load_features()

    print("Preparing TFT panel...")
    df, known_reals, unknown_reals = prepare_tft_panel(raw)

    print("Checking target variation...")
    if df[TARGET].nunique() < 5:
        raise ValueError("congestion_index has too few unique values for TFT training.")

    model, training_dataset = train_tft(
        df=df,
        known_reals=known_reals,
        unknown_reals=unknown_reals,
        horizon=args.horizon,
        encoder_length=args.encoder_length,
        max_epochs=args.epochs,
        batch_size=args.batch_size,
        accelerator=args.accelerator,
    )

    print("Forecasting future horizon...")
    forecast = forecast_future(
        model=model,
        training_dataset=training_dataset,
        df=df,
        known_reals=known_reals,
        unknown_reals=unknown_reals,
        horizon=args.horizon,
        batch_size=args.batch_size,
    )

    validate_forecast(forecast, args.horizon)

    out_path = OUTPUT_DIR / "tft_forecast.csv"
    forecast.to_csv(out_path, index=False)

    metadata = {
        "model": "tft",
        "target": TARGET,
        "quantiles": QUANTILES,
        "horizon": args.horizon,
        "encoder_length": args.encoder_length,
        "epochs": args.epochs,
        "ports": int(forecast["port_id"].nunique()),
        "forecast_rows": int(len(forecast)),
        "known_reals": known_reals,
        "unknown_reals": unknown_reals,
    }

    with open(MODEL_DIR / "tft_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, default=str)

    print()
    print(f"Wrote {out_path}")
    print(f"Wrote {MODEL_DIR / 'tft_metadata.json'}")
    print()
    print("TFT forecast summary")
    print("--------------------")
    print(f"Rows: {len(forecast):,}")
    print(f"Ports: {forecast['port_id'].nunique()}")
    print(f"Horizon days: {forecast['horizon_day'].min()}-{forecast['horizon_day'].max()}")
    print()
    print("Model counts:")
    print(forecast["model"].value_counts())
    print()
    print("Sample:")
    print(forecast.head(20))


if __name__ == "__main__":
    main()