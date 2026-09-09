"""Adaptive multi-member forecast ensemble with a leakage-safe weighting policy.

Which model wins depends entirely on lead time. The walk-forward benchmark for
this system showed naive persistence beating every learned model out to day 5
and losing to the boosted quantile model from day 6 onward -- an ordinary result
for a smoothed, strongly autocorrelated index, and one a single fixed blend
cannot exploit. So the ensemble is a **stacker over horizon**:

    members        persistence, the GBM quantile model, and a second opinion
                   (the TFT when the deep stack is installed, otherwise a
                   regularised linear quantile model)
    weights        fitted per horizon -- and optionally per regime and per port
                   -- by minimising pinball loss on out-of-fold predictions only
    calibration    a per-horizon conformal offset measured on the blended bands

Nothing here is tuned on the evaluation block, and when no fitted policy exists
the ensemble falls back to an explicit equal weighting and says so rather than
implying a tuned weight. The policy artefact lives at
``outputs/forecasts/ensemble_weights.json`` and is produced by
:mod:`src.evaluation.model_benchmark`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from src.utils.config import PORT_ID

#: Canonical member names. The policy is keyed by these.
PERSISTENCE = "persistence"
GBM = "gbm"
SECOND_OPINION = "second"

DEFAULT_MEMBERS = (PERSISTENCE, GBM, SECOND_OPINION)

#: No single member may be silenced entirely by a small validation sample.
MIN_WEIGHT, MAX_WEIGHT = 0.15, 0.85

#: Retained for the two-model call path used by older code and tests.
PRIOR_TFT_WEIGHT = 0.5

_BLEND_COLUMNS = ("q10", "q50", "q90")


@dataclass
class EnsemblePolicy:
    """Fitted member weights, and an honest record of where they came from."""

    members: List[str] = field(default_factory=lambda: list(DEFAULT_MEMBERS))
    global_weights: Dict[str, float] = field(default_factory=dict)
    by_horizon: Dict[int, Dict[str, float]] = field(default_factory=dict)
    by_regime: Dict[str, Dict[str, float]] = field(default_factory=dict)
    by_port: Dict[str, Dict[str, float]] = field(default_factory=dict)
    conformal_by_horizon: Dict[int, float] = field(default_factory=dict)
    fitted: bool = False
    source: str = "equal weighting (no benchmark artefact found)"
    folds: int = 0
    generated_at: Optional[str] = None
    second_opinion_model: Optional[str] = None

    # -- resolution ---------------------------------------------------------
    def _equal(self) -> Dict[str, float]:
        share = 1.0 / max(len(self.members), 1)
        return {m: share for m in self.members}

    def weights_for(self, horizon: int | None = None,
                    regime: str | None = None,
                    port_id: str | None = None) -> Dict[str, float]:
        """Resolve member weights, most specific evidence first."""
        weights = dict(self.global_weights or self._equal())
        if horizon is not None and int(horizon) in self.by_horizon:
            weights = dict(self.by_horizon[int(horizon)])

        # Regime and port are gentle adjustments around the horizon weights --
        # there is far less data per cell, so they never fully override.
        adjustments = []
        if regime and regime in self.by_regime:
            adjustments.append(self.by_regime[regime])
        if port_id and str(port_id) in self.by_port:
            adjustments.append(self.by_port[str(port_id)])
        if adjustments:
            blended = {}
            for member in weights:
                other = float(np.mean([a.get(member, weights[member])
                                       for a in adjustments]))
                blended[member] = 0.6 * weights[member] + 0.4 * other
            weights = blended
        return _normalise(weights)

    def conformal_for(self, horizon: int | None) -> float:
        if horizon is None:
            return 0.0
        return float(self.conformal_by_horizon.get(int(horizon), 0.0))

    # -- reporting ----------------------------------------------------------
    def describe(self) -> str:
        if not self.fitted:
            return f"unfitted ({self.source})"
        head = ", ".join(f"{m}={w:.2f}" for m, w in
                         sorted(self.global_weights.items(), key=lambda kv: -kv[1]))
        return (f"fitted on {self.folds} walk-forward folds; global {head}; "
                f"{len(self.by_horizon)} horizon-specific weight sets")

    def to_dict(self) -> dict:
        return {
            "members": list(self.members),
            "globalWeights": {k: round(v, 4) for k, v in self.global_weights.items()},
            "byHorizon": {str(h): {k: round(v, 4) for k, v in w.items()}
                          for h, w in sorted(self.by_horizon.items())},
            "byRegime": {r: {k: round(v, 4) for k, v in w.items()}
                         for r, w in self.by_regime.items()},
            "byPort": {p: {k: round(v, 4) for k, v in w.items()}
                       for p, w in self.by_port.items()},
            "conformalByHorizon": {str(h): round(v, 3)
                                   for h, v in sorted(self.conformal_by_horizon.items())},
            "fitted": self.fitted,
            "source": self.source,
            "folds": self.folds,
            "generatedAt": self.generated_at,
            "secondOpinionModel": self.second_opinion_model,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "EnsemblePolicy":
        return cls(
            members=[str(m) for m in payload.get("members", DEFAULT_MEMBERS)],
            global_weights={str(k): float(v) for k, v in
                            (payload.get("globalWeights") or {}).items()},
            by_horizon={int(h): {str(k): float(v) for k, v in w.items()}
                        for h, w in (payload.get("byHorizon") or {}).items()},
            by_regime={str(r): {str(k): float(v) for k, v in w.items()}
                       for r, w in (payload.get("byRegime") or {}).items()},
            by_port={str(p): {str(k): float(v) for k, v in w.items()}
                     for p, w in (payload.get("byPort") or {}).items()},
            conformal_by_horizon={int(h): float(v) for h, v in
                                  (payload.get("conformalByHorizon") or {}).items()},
            fitted=bool(payload.get("fitted", False)),
            source=str(payload.get("source", "loaded policy")),
            folds=int(payload.get("folds", 0)),
            generated_at=payload.get("generatedAt"),
            second_opinion_model=payload.get("secondOpinionModel"),
        )


def _normalise(weights: Dict[str, float]) -> Dict[str, float]:
    clipped = {k: float(np.clip(v, 0.0, 1.0)) for k, v in weights.items()}
    total = sum(clipped.values())
    if total <= 1e-9:
        share = 1.0 / max(len(clipped), 1)
        return {k: share for k in clipped}
    return {k: v / total for k, v in clipped.items()}


def load_ensemble_policy(path: str | Path | None) -> EnsemblePolicy:
    """Load the fitted policy, or return the explicit equal-weight fallback."""
    if path is None:
        return EnsemblePolicy()
    p = Path(path)
    if not p.exists():
        return EnsemblePolicy()
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return EnsemblePolicy.from_dict(json.load(fh))
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return EnsemblePolicy()


# ---------------------------------------------------------------------------
# Blending
# ---------------------------------------------------------------------------
def blend_members(frames: Dict[str, pd.DataFrame],
                  policy: EnsemblePolicy,
                  panel: pd.DataFrame | None = None,
                  secondary_from: str = GBM) -> pd.DataFrame:
    """Blend any number of aligned member forecasts into the ensemble output.

    ``frames`` maps member name -> forecast table. Every table must share the
    ``(port_id, horizon_day)`` key and carry q10/q50/q90. Secondary targets
    (delay, throughput) are taken from ``secondary_from``, because only that
    member forecasts them.
    """
    present = {name: frame for name, frame in frames.items()
               if frame is not None and not frame.empty}
    if not present:
        raise ValueError("blend_members: no member forecasts supplied")
    if len(present) == 1:
        only = next(iter(present.values())).copy()
        only["model"] = "adaptive_ensemble"
        only["ensemble_members"] = next(iter(present))
        only["model_disagreement"] = 0.0
        return only.reset_index(drop=True)

    keys = [PORT_ID, "horizon_day"]
    anchor_name = secondary_from if secondary_from in present else next(iter(present))
    out = present[anchor_name].copy()

    member_quantiles: Dict[str, pd.DataFrame] = {}
    for name, frame in present.items():
        cols = keys + [c for c in _BLEND_COLUMNS if c in frame.columns]
        aligned = out[keys].merge(frame[cols], on=keys, how="left")
        member_quantiles[name] = aligned

    regime_by_port = _regime_context(panel)
    weights = np.array([
        [policy.weights_for(horizon=row.horizon_day,
                            regime=regime_by_port.get(str(getattr(row, PORT_ID))),
                            port_id=getattr(row, PORT_ID)).get(name, 0.0)
         for name in present]
        for row in out.itertuples()
    ], dtype=float)
    weights = weights / np.clip(weights.sum(axis=1, keepdims=True), 1e-9, None)

    names = list(present)
    for column in _BLEND_COLUMNS:
        stack = np.column_stack([
            pd.to_numeric(member_quantiles[name][column], errors="coerce").to_numpy()
            for name in names
        ])
        # A member missing a row must not drag the blend toward zero: renormalise
        # over the members that actually produced a value.
        mask = ~np.isnan(stack)
        row_weights = np.where(mask, weights, 0.0)
        totals = np.clip(row_weights.sum(axis=1, keepdims=True), 1e-9, None)
        out[column] = np.nansum(np.nan_to_num(stack) * row_weights, axis=1) / totals[:, 0]

    offsets = out["horizon_day"].map(policy.conformal_for).astype(float).to_numpy()
    out["q10"] = np.clip(out["q10"].to_numpy() - offsets, 0.0, None)
    out["q90"] = out["q90"].to_numpy() + offsets
    out["conformal_offset"] = np.round(offsets, 3)

    quantiles = np.sort(out[list(_BLEND_COLUMNS)].to_numpy(dtype=float), axis=1)
    out[list(_BLEND_COLUMNS)] = quantiles
    out["predicted_congestion"] = out["q50"]

    # Disagreement: the spread of member medians relative to the blended band.
    medians = np.column_stack([
        pd.to_numeric(member_quantiles[name]["q50"], errors="coerce").to_numpy()
        for name in names
    ])
    spread = np.nanmax(medians, axis=1) - np.nanmin(medians, axis=1)
    band = np.clip((out["q90"] - out["q10"]).to_numpy(dtype=float), 1.0, None)
    disagreement = np.clip(spread / band, 0.0, 1.0)

    base_confidence = np.zeros(len(out), dtype=float)
    for index, name in enumerate(names):
        frame = present[name]
        confidence = (pd.to_numeric(frame.get("confidence_score"), errors="coerce")
                      if "confidence_score" in frame else None)
        if confidence is None:
            values = np.full(len(out), 0.7)
        else:
            aligned = out[keys].merge(frame[keys + ["confidence_score"]],
                                      on=keys, how="left")
            values = pd.to_numeric(aligned["confidence_score"],
                                   errors="coerce").fillna(0.7).to_numpy()
        base_confidence += weights[:, index] * values

    out["confidence_score"] = np.clip(
        base_confidence * (1.0 - 0.30 * disagreement), 0.05, 0.98).round(3)

    out["model"] = "adaptive_ensemble"
    out["model_disagreement"] = np.round(disagreement, 3)
    out["ensemble_members"] = ",".join(names)
    out["ensemble_policy"] = policy.source
    for index, name in enumerate(names):
        out[f"weight_{name}"] = np.round(weights[:, index], 3)
    return out.reset_index(drop=True)


def blend_forecasts(tft: pd.DataFrame,
                    baseline: pd.DataFrame,
                    tft_weight: float | None = None,
                    baseline_weight: float | None = None,
                    *,
                    policy: EnsemblePolicy | None = None,
                    panel: pd.DataFrame | None = None) -> pd.DataFrame:
    """Two-member blend, kept for the deep-model path and for direct callers.

    Pass an explicit ``tft_weight`` for a fixed blend, or a ``policy`` to use the
    fitted horizon-aware weights.
    """
    if tft_weight is not None:
        weight = float(tft_weight)
        other = 1.0 - weight if baseline_weight is None else float(baseline_weight)
        total = max(weight + other, 1e-9)
        policy = EnsemblePolicy(
            members=[SECOND_OPINION, GBM],
            global_weights={SECOND_OPINION: weight / total, GBM: other / total},
            fitted=False,
            source=f"explicit fixed weight ({weight / total:.2f} / {other / total:.2f})")
    elif policy is None:
        policy = EnsemblePolicy(members=[SECOND_OPINION, GBM])

    restricted = EnsemblePolicy(
        members=[SECOND_OPINION, GBM],
        global_weights=_restrict(policy.weights_for(), [SECOND_OPINION, GBM]),
        by_horizon={h: _restrict(w, [SECOND_OPINION, GBM])
                    for h, w in policy.by_horizon.items()},
        by_regime={r: _restrict(w, [SECOND_OPINION, GBM])
                   for r, w in policy.by_regime.items()},
        by_port={p: _restrict(w, [SECOND_OPINION, GBM])
                 for p, w in policy.by_port.items()},
        conformal_by_horizon=dict(policy.conformal_by_horizon),
        fitted=policy.fitted, source=policy.source, folds=policy.folds,
        generated_at=policy.generated_at,
        second_opinion_model=policy.second_opinion_model)

    return blend_members({SECOND_OPINION: tft, GBM: baseline}, restricted,
                         panel=panel, secondary_from=GBM)


def _restrict(weights: Dict[str, float], members: Iterable[str]) -> Dict[str, float]:
    subset = {m: float(weights.get(m, 0.0)) for m in members}
    return _normalise(subset)


def _regime_context(panel: pd.DataFrame | None) -> Dict[str, str]:
    """Latest regime label per port, used to resolve regime-aware weights."""
    if panel is None or panel.empty:
        return {}
    frame = panel.copy()
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.sort_values("date")
    latest = frame.groupby(PORT_ID, as_index=False).tail(1)
    context: Dict[str, str] = {}
    for _, row in latest.iterrows():
        label = _regime_label(row)
        if label:
            context[str(row[PORT_ID])] = label
    return context


def _regime_label(row) -> str | None:
    for column in ("regime_label", "regime"):
        value = row.get(column)
        if isinstance(value, str) and value:
            return value
    probs = {"NORMAL": row.get("p_normal"), "CONGESTED": row.get("p_congested"),
             "SEVERE": row.get("p_severe")}
    usable = {k: float(v) for k, v in probs.items()
              if v is not None and not pd.isna(v)}
    return max(usable, key=usable.get) if usable else None


def weights_from_benchmark(path: str | Path | None,
                           default_tft: float = PRIOR_TFT_WEIGHT
                           ) -> tuple[float, float]:
    """Back-compatible helper returning ``(second_opinion_weight, gbm_weight)``."""
    if path is None:
        return default_tft, 1.0 - default_tft
    p = Path(path)
    policy = load_ensemble_policy(p.parent / "ensemble_weights.json")
    if policy.fitted:
        weights = _restrict(policy.weights_for(), [SECOND_OPINION, GBM])
        return weights[SECOND_OPINION], weights[GBM]
    return default_tft, 1.0 - default_tft
