"""Temporal Fusion Transformer (TFT) -- the real, trainable core model.

This is the centerpiece forecasting model. It is implemented on top of
`pytorch-forecasting`'s `TemporalFusionTransformer`, which gives us:

  * multi-horizon (1..10 day) forecasting in a single model,
  * native **quantile regression** (q10/q50/q90) via QuantileLoss,
  * learned variable selection + interpretable attention,
  * per-group (per-port) normalisation.

Design choices
--------------
* Single primary target (congestion_index) for robustness; secondary targets
  (delay/throughput) are produced by the baseline in a hybrid (see
  forecast_runner.generate_forecast). Multi-target TFT is a one-line change
  (pass a list to `target=`) and is documented inline.
* **Known-future reals**  = calendar + weather-risk (a weather forecast is
  available at origin time, so these are legitimately known into the future).
* **Unknown reals**       = the target + expert/regime features (only observed
  up to "now").
* If torch/pytorch-forecasting is not installed, the class still imports; only
  fit/predict raise, and forecast_runner falls back to the baseline.

The output of `predict_future()` matches the exact schema the rest of the
pipeline (dashboard, decision layer, user outputs) consumes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

from src.forecasting.tft_dataset import CALENDAR_COLS, add_calendar_features
from src.utils.config import (
    DATE,
    FORECAST_HORIZON_DAYS,
    PORT_ID,
    PRIMARY_TARGET,
    QUANTILES,
    RANDOM_SEED,
    static_features_frame,
)
from src.utils.logging_utils import get_logger

log = get_logger(__name__)


def torch_available() -> bool:
    try:
        import torch  # noqa: F401
        import pytorch_forecasting  # noqa: F401
        import lightning  # noqa: F401
        return True
    except Exception:
        try:  # older pytorch-forecasting shipped pytorch_lightning
            import torch  # noqa: F401
            import pytorch_forecasting  # noqa: F401
            import pytorch_lightning  # noqa: F401
            return True
        except Exception:
            return False


# Known-future weather columns we expose to the decoder.
_WX_KNOWN = ["WxImpactIndex", "wind_risk", "rain_risk", "wave_risk", "storm_risk"]

# Unknown (encoder-only) expert/regime/macro features.
_UNKNOWN_REALS = [
    "geo_risk_score", "news_sentiment_score", "strike_risk", "policy_risk",
    "conflict_risk", "event_spike_score", "queue_proxy", "turnaround_proxy",
    "vessel_density", "avg_speed_near_port", "anchorage_count",
    "demand_pressure", "trade_trend", "utilization",
    # macro / conditions -> the TFT reacts to oil, currency, inflation, news
    "oil_stress", "fx_stress", "inflation_stress", "news_stress",
    "p_normal", "p_congested", "p_severe", "days_in_state",
    "expected_remaining_days", "transition_risk", "regime_confidence",
    # specialist agents -- the deep model sees the same evidence as the GBM
    "capacity_pressure", "queue_momentum", "throughput_stress", "anomaly_score",
    "arrival_acceleration", "arrival_clustering", "anchorage_buildup",
    "berth_pressure", "disruption_exposure", "disruption_pressure",
    "weather_shock", "weather_persistence", "specialist_stress",
    "data_quality_score",
]

_STATIC_REALS = ["port_capacity", "berth_count", "connectivity_score"]

# Inference must not attach a Lightning logger: recent Lightning versions raise
# on the sentinel value pytorch-forecasting logs during predict, which would
# otherwise take the whole deep-model path down for a cosmetic reason.
_PREDICT_TRAINER_KWARGS = {
    "logger": False,
    "enable_progress_bar": False,
    "enable_model_summary": False,
    "enable_checkpointing": False,
    "accelerator": "cpu",
    "devices": 1,
}


@dataclass
class TFTConfig:
    target: str = PRIMARY_TARGET
    horizon: int = FORECAST_HORIZON_DAYS
    encoder_length: int = 30
    quantiles: Optional[List[float]] = None
    hidden_size: int = 32
    attention_head_size: int = 2
    dropout: float = 0.15
    hidden_continuous_size: int = 16
    learning_rate: float = 3e-3
    max_epochs: int = 40
    batch_size: int = 128
    seed: int = RANDOM_SEED


class TFTForecaster:
    """Trainable TFT wrapper with the same forecast schema as the baseline."""

    def __init__(self, config: TFTConfig | None = None):
        self.cfg = config or TFTConfig()
        self.cfg.quantiles = self.cfg.quantiles or QUANTILES
        self.available = torch_available()
        self.training_dataset = None
        self.model = None
        self.trainer = None
        self._known_reals: List[str] = []
        self._unknown_reals: List[str] = []
        self._max_time_idx: dict = {}

    # ------------------------------------------------------------- prepare
    def _prepare_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        """Daily, gap-free, per-port frame with time_idx + calendar + static."""
        df = panel.copy()
        df[DATE] = pd.to_datetime(df[DATE])
        df = df.sort_values([PORT_ID, DATE])

        # Reindex each port to a continuous daily grid (fill gaps) so time_idx
        # is contiguous (a TimeSeriesDataSet requirement).
        filled = []
        for pid, g in df.groupby(PORT_ID, sort=False):
            full = pd.date_range(g[DATE].min(), g[DATE].max(), freq="D")
            g = g.set_index(DATE).reindex(full)
            g[PORT_ID] = pid
            g.index.name = DATE
            g = g.reset_index()
            g = g.ffill().bfill()
            filled.append(g)
        df = pd.concat(filled, ignore_index=True)

        df["time_idx"] = (df.groupby(PORT_ID)[DATE]
                          .transform(lambda s: (s - s.min()).dt.days).astype(int))
        df = add_calendar_features(df, DATE)

        # static features
        static = static_features_frame()[[PORT_ID] + _STATIC_REALS]
        df = df.merge(static, on=PORT_ID, how="left")
        df[PORT_ID] = df[PORT_ID].astype(str)
        self._max_time_idx = df.groupby(PORT_ID)["time_idx"].max().to_dict()
        return df

    def _role_columns(self, df: pd.DataFrame):
        """Resolve the covariate roles, dropping anything the feed cannot supply.

        TimeSeriesDataSet rejects NaNs outright, and a real deployment always has
        some column the current source cannot fill -- PortWatch, for instance,
        carries no vessel speed at all. Columns that are entirely missing are
        dropped (they carry no information anyway) and partial gaps are filled
        forward within each port, so an incomplete feed degrades the model
        instead of aborting the run.
        """
        known = [c for c in CALENDAR_COLS + _WX_KNOWN if c in df.columns]
        unknown = [c for c in _UNKNOWN_REALS if c in df.columns]

        df[self.cfg.target] = pd.to_numeric(df[self.cfg.target], errors="coerce")
        for c in known + unknown + _STATIC_REALS:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)

        dropped = [c for c in known + unknown if df[c].isna().all()]
        if dropped:
            log.info("TFT: dropping %d all-missing covariates (%s).",
                     len(dropped), ", ".join(sorted(dropped)))
        known = [c for c in known if c not in dropped]
        unknown = [c for c in unknown if c not in dropped]

        for c in known + unknown:
            if df[c].isna().any():
                df[c] = (df.groupby(PORT_ID)[c].transform(
                    lambda s: s.ffill().bfill()).fillna(0.0))
        for c in _STATIC_REALS:
            if c in df.columns:
                df[c] = df[c].fillna(df[c].median()).fillna(0.0)
        df[self.cfg.target] = (df.groupby(PORT_ID)[self.cfg.target]
                               .transform(lambda s: s.ffill().bfill()))
        return known, unknown

    # ------------------------------------------------------------------ fit
    def fit(self, panel: pd.DataFrame, weather_now: pd.DataFrame | None = None):
        if not self.available:
            raise RuntimeError("PyTorch/pytorch-forecasting/lightning not installed.")
        import torch
        from pytorch_forecasting import TemporalFusionTransformer, TimeSeriesDataSet
        from pytorch_forecasting.data import GroupNormalizer
        from pytorch_forecasting.metrics import QuantileLoss
        try:
            from lightning.pytorch import Trainer, seed_everything
            from lightning.pytorch.callbacks import EarlyStopping
        except Exception:  # older API
            from pytorch_lightning import Trainer, seed_everything
            from pytorch_lightning.callbacks import EarlyStopping

        seed_everything(self.cfg.seed, workers=True)
        df = self._prepare_panel(panel)
        known, unknown = self._role_columns(df)
        self._known_reals, self._unknown_reals = known, unknown

        # target must be in the unknown reals list for the encoder
        unknown_with_target = list(dict.fromkeys([self.cfg.target] + unknown))

        max_time = int(df["time_idx"].max())
        training_cutoff = max_time - self.cfg.horizon

        self.training_dataset = TimeSeriesDataSet(
            df[df["time_idx"] <= training_cutoff],
            time_idx="time_idx",
            target=self.cfg.target,                 # -> [list] for multi-target
            group_ids=[PORT_ID],
            max_encoder_length=self.cfg.encoder_length,
            max_prediction_length=self.cfg.horizon,
            static_categoricals=[PORT_ID],
            static_reals=_STATIC_REALS,
            time_varying_known_reals=["time_idx"] + known,
            time_varying_unknown_reals=unknown_with_target,
            target_normalizer=GroupNormalizer(groups=[PORT_ID], transformation="softplus"),
            add_relative_time_idx=True,
            add_target_scales=True,
            add_encoder_length=True,
            allow_missing_timesteps=True,
        )
        validation = TimeSeriesDataSet.from_dataset(
            self.training_dataset, df, predict=True, stop_randomization=True)

        train_loader = self.training_dataset.to_dataloader(
            train=True, batch_size=self.cfg.batch_size, num_workers=0)
        val_loader = validation.to_dataloader(
            train=False, batch_size=self.cfg.batch_size, num_workers=0)

        self.model = TemporalFusionTransformer.from_dataset(
            self.training_dataset,
            learning_rate=self.cfg.learning_rate,
            hidden_size=self.cfg.hidden_size,
            attention_head_size=self.cfg.attention_head_size,
            dropout=self.cfg.dropout,
            hidden_continuous_size=self.cfg.hidden_continuous_size,
            loss=QuantileLoss(self.cfg.quantiles),
            log_interval=0,
            optimizer="adam",
        )

        early = EarlyStopping(monitor="val_loss", patience=6, mode="min")
        self.trainer = Trainer(
            max_epochs=self.cfg.max_epochs,
            accelerator="auto",
            gradient_clip_val=0.1,
            callbacks=[early],
            enable_progress_bar=True,
            enable_checkpointing=False,
            logger=False,
        )
        log.info("Training TFT (target=%s, epochs<=%d)...",
                 self.cfg.target, self.cfg.max_epochs)
        self.trainer.fit(self.model, train_dataloaders=train_loader,
                         val_dataloaders=val_loader)
        log.info("TFT training complete.")
        self._df_prepared = df
        return self

    # -------------------------------------------------------------- predict
    def _extend_future(self, df: pd.DataFrame, weather_now) -> pd.DataFrame:
        """Append `horizon` future rows per port with known reals filled and the
        target left as NaN, so the TFT decoder can forecast truly unseen days."""
        future_rows = []
        wx_lookup = None
        if weather_now is not None and not weather_now.empty:
            w = weather_now.copy()
            if "horizon_day" in w.columns:
                w = w[w["horizon_day"] == 0]
            w[DATE] = pd.to_datetime(w[DATE])
            wx_lookup = w.set_index([PORT_ID, DATE])

        for pid, g in df.groupby(PORT_ID, sort=False):
            last = g.iloc[-1]
            last_date = pd.to_datetime(last[DATE])
            last_idx = int(last["time_idx"])
            last_target = last[self.cfg.target]
            for h in range(1, self.cfg.horizon + 1):
                row = last.copy()
                row[DATE] = last_date + pd.Timedelta(days=h)
                row["time_idx"] = last_idx + h
                # The decoder target is what we predict; pytorch-forecasting still
                # requires it to be non-NaN to build the dataset, so we seed it
                # with a persistence placeholder (the model overwrites it).
                row[self.cfg.target] = last_target
                future_rows.append(row)
        fut = pd.DataFrame(future_rows)
        fut = add_calendar_features(fut.drop(columns=CALENDAR_COLS, errors="ignore"), DATE)
        if wx_lookup is not None:
            for c in _WX_KNOWN:
                if c in wx_lookup.columns:
                    fut[c] = [wx_lookup[c].get((p, d), np.nan)
                              for p, d in zip(fut[PORT_ID], pd.to_datetime(fut[DATE]))]
        ext = pd.concat([df, fut], ignore_index=True)
        # fill any remaining NaNs in ALL columns (incl. target placeholder) per port
        cols = [c for c in ext.columns if c not in (DATE, PORT_ID)]
        ext[cols] = ext.groupby(PORT_ID)[cols].ffill().bfill()
        return ext

    def predict_future(self, panel: pd.DataFrame,
                       weather_now: pd.DataFrame | None = None) -> pd.DataFrame:
        """Forecast the next `horizon` days beyond the last observed date."""
        if self.model is None:
            raise RuntimeError("Call fit() before predict_future().")
        from pytorch_forecasting import TimeSeriesDataSet

        df = self._prepare_panel(panel)
        self._role_columns(df)

        # Preferred path: append true future rows (target=NaN) and decode them.
        # Some pytorch-forecasting versions are fussy about NaN decode targets;
        # if that fails we fall back to forecasting the last observed window,
        # which still demonstrates the trained TFT end-to-end.
        try:
            ext = self._extend_future(df, weather_now)
            pred_ds = TimeSeriesDataSet.from_dataset(
                self.training_dataset, ext, predict=True, stop_randomization=True)
            loader = pred_ds.to_dataloader(train=False,
                                           batch_size=self.cfg.batch_size,
                                           num_workers=0)
            raw = self.model.predict(loader, mode="quantiles", return_index=True,
                                     trainer_kwargs=_PREDICT_TRAINER_KWARGS)
            return self._to_forecast_table(raw, ext)
        except Exception as exc:
            log.warning("TFT future-decode failed (%s); forecasting last "
                        "observed window instead.", exc)
            pred_ds = TimeSeriesDataSet.from_dataset(
                self.training_dataset, df, predict=True, stop_randomization=True)
            loader = pred_ds.to_dataloader(train=False,
                                           batch_size=self.cfg.batch_size,
                                           num_workers=0)
            raw = self.model.predict(loader, mode="quantiles", return_index=True,
                                     trainer_kwargs=_PREDICT_TRAINER_KWARGS)
            return self._to_forecast_table(raw, df)

    def _to_forecast_table(self, raw, df_prepared) -> pd.DataFrame:
        """Convert pytorch-forecasting quantile output to our forecast schema."""
        quantiles = raw.output if hasattr(raw, "output") else raw[0]
        index = raw.index if hasattr(raw, "index") else raw[1]
        q = np.asarray(quantiles)            # (n_series, horizon, n_quantiles)
        if q.ndim == 2:
            q = q[:, :, None]
        qidx = {round(qq, 2): i for i, qq in enumerate(self.cfg.quantiles)}

        rows = []
        for s in range(q.shape[0]):
            pid = str(index.iloc[s][PORT_ID])
            base_time = int(index.iloc[s]["time_idx"])  # first decoded time_idx
            origin_idx = base_time - 1
            # map time_idx back to a calendar date for this port
            port_df = df_prepared[df_prepared[PORT_ID] == pid]
            t0 = port_df[DATE].min()
            origin_date = pd.to_datetime(t0) + pd.Timedelta(days=origin_idx)
            for h in range(q.shape[1]):
                q10 = q[s, h, qidx.get(0.1, 0)]
                q50 = q[s, h, qidx.get(0.5, 0)]
                q90 = q[s, h, qidx.get(0.9, q.shape[2] - 1)]
                q10, q50, q90 = sorted([float(q10), float(q50), float(q90)])
                rows.append({
                    PORT_ID: pid,
                    "forecast_origin_date": origin_date,
                    "target_date": origin_date + pd.Timedelta(days=h + 1),
                    "horizon_day": h + 1,
                    "predicted_congestion": round(q50, 3),
                    "predicted_delay": np.nan,      # filled by baseline (hybrid)
                    "predicted_throughput": np.nan,
                    "q10": round(q10, 3), "q50": round(q50, 3), "q90": round(q90, 3),
                })
        out = pd.DataFrame(rows)
        out = _add_tft_risk_confidence(out)
        return out

    # --------------------------------------------------------- interpretation
    def variable_importance(self) -> dict:
        """Return TFT encoder/decoder/static variable-selection weights."""
        if self.model is None:
            return {}
        try:
            from pytorch_forecasting import TimeSeriesDataSet
            val = TimeSeriesDataSet.from_dataset(
                self.training_dataset, self._df_prepared, predict=True,
                stop_randomization=True)
            loader = val.to_dataloader(train=False, batch_size=self.cfg.batch_size)
            raw, = self.model.predict(loader, mode="raw", return_x=False),
            interp = self.model.interpret_output(raw, reduction="sum")
            return {k: (v.detach().cpu().numpy().tolist()
                        if hasattr(v, "detach") else v)
                    for k, v in interp.items()}
        except Exception as exc:  # pragma: no cover
            log.warning("TFT interpretation failed: %s", exc)
            return {}


def _add_tft_risk_confidence(out: pd.DataFrame) -> pd.DataFrame:
    cong = out["predicted_congestion"].to_numpy(dtype=float)
    q90 = out["q90"].to_numpy(dtype=float)

    def level(p, hi):
        if p >= 60 or hi >= 75:
            return "High"
        if p >= 40 or hi >= 55:
            return "Medium"
        return "Low"
    out["risk_level"] = [level(p, h) for p, h in zip(cong, q90)]
    width = (out["q90"] - out["q10"]).to_numpy(dtype=float)
    width_term = np.clip(1.0 - width / 60.0, 0.1, 1.0)
    horizon_term = 1.0 - 0.03 * out["horizon_day"].to_numpy(dtype=float)
    out["confidence_score"] = np.clip(width_term * horizon_term, 0.05, 0.97).round(3)
    return out
