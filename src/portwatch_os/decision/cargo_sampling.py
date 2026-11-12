"""Cargo extension of the paired commercial uncertainty study.

A scramble is an independent replicate. Each option consumes the same worlds,
including the same uniform event draws, and study results exclude runtimes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from datetime import datetime
from functools import lru_cache
from typing import Annotated, Literal

import numpy as np
from pydantic import Field, field_validator, model_validator
from scipy.special import ndtr, ndtri
from scipy.stats import qmc, t

from .cargo_risk import (
    CostBreakdown, CostState, ConsignmentLoss, FloatArray, combine_costs, cvar,
    evaluate_consignment, summarize_cost,
)
from .commercial import Consignment, Currency, Strict, digest, instant
from .commercial_uncertainty import DelayDistribution
from .outcome import queue_wait_hours

VERSION = "cargo-paired-sobol-v1"
DIMENSIONS = 8
DESIGN = "Gaussian copula: port = .20 closure + .35 weather + residual; handling = .40 port + residual; FX = .20 fuel + residual"
FALLBACK = "ASSUMPTION · no retained ensemble; triangular weather delay 0/2/6 h"


class ClosureBasis(Strict):
    startedHour: float = Field(default=0, le=0, ge=-8760)
    medianHours: float = Field(ge=0, le=8760)
    logSigma: float = Field(default=.55, ge=0, le=2)
    fizzleProbability: float = Field(default=0, ge=0, le=1)
    drainFraction: float = Field(default=.715, ge=0, le=2)
    source: str = Field(min_length=3, max_length=400)


class WeatherMembers(Strict):
    windKn: tuple[Annotated[float, Field(ge=0, le=300)], ...] = Field(min_length=2, max_length=100)
    source: str
    delayHoursPerExcessKnot: float = Field(default=.22, ge=0, le=5)
    thresholdKnots: float = Field(default=15, ge=0, le=150)


class PortQuantiles(Strict):
    congestion: tuple[float, float, float]
    medianWaitHours: float = Field(ge=0, le=8760)
    waitHoursPerIndexPoint: float = Field(ge=0, le=20)
    source: str

    @field_validator("congestion")
    @classmethod
    def ordered(cls, value):
        low, median, high = value
        if not 0 <= low <= median <= high <= 100:
            raise ValueError("Congestion quantiles must be ordered on the 0–100 scale")
        return value


class FuelRange(Strict):
    low: float = Field(ge=0)
    high: float = Field(ge=0)
    currency: Currency
    source: str

    @model_validator(mode="after")
    def ordered(self):
        if self.high < self.low:
            raise ValueError("Fuel range high must be at least low")
        return self


class FXHistory(Strict):
    # Paired, same-date units of currency per EUR, after availability checks.
    datedQuotes: tuple[dict[str, float], ...] = Field(min_length=1, max_length=365)
    source: str

    @field_validator("datedQuotes")
    @classmethod
    def valid_quotes(cls, value):
        if any(row.keys() != {"EUR", "USD", "INR"} or row["EUR"] != 1
               or any(not np.isfinite(rate) or rate <= 0 for rate in row.values()) for row in value):
            raise ValueError("FX history requires paired positive EUR/USD/INR legs")
        return value


class RiskOption(Strict):
    id: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=180)
    action: str = Field(min_length=1, max_length=100)
    cleanDeliveryHours: float = Field(ge=0, le=87600)
    reachClosureHour: float | None = Field(default=None, ge=-8760, le=8760)
    areas: tuple[str, ...] | None = None
    weather: WeatherMembers | None = None
    port: PortQuantiles | None = None
    weatherExposure: float = Field(default=1, ge=0, le=4)
    handlingExposure: float = Field(default=1, ge=0, le=4)
    berthExposure: float = Field(default=1, ge=0, le=4)
    dwellHours: float | None = Field(default=None, ge=0, le=8760)
    detentionHours: float | None = Field(default=None, ge=0, le=8760)
    unpoweredHours: float | None = Field(default=None, ge=0, le=8760)
    fuelTonnes: float | None = Field(default=None, ge=0, le=100000)
    fixedVoyageCost: float | None = Field(default=None, ge=0, le=1e9)
    latestStartHour: float | None = Field(default=None, ge=0, le=8760)
    source: str


class RiskStudy(Strict):
    problemId: str
    at: datetime
    reportingCurrency: Currency
    keepOptionId: str
    plannedDeliveryHours: float = Field(ge=0, le=87600)
    options: tuple[RiskOption, ...] = Field(min_length=1, max_length=10)
    consignments: tuple[Consignment, ...] = Field(min_length=0, max_length=24)
    closure: ClosureBasis
    handling: DelayDistribution
    fuel: FuelRange | None = None
    fx: FXHistory | None = None
    timeCostPerHour: float | None = Field(default=None, ge=0, le=1e7)
    timeCostBasis: str | None = None
    nextRefreshHour: float | None = Field(default=None, gt=0, le=72)
    scope: str

    @field_validator("at")
    @classmethod
    def aware(cls, value):
        return instant(value)

    @model_validator(mode="after")
    def ids(self):
        options = {option.id for option in self.options}
        if len(options) != len(self.options) or self.keepOptionId not in options:
            raise ValueError("A distinct option list and its current plan are required")
        if len({cargo.id for cargo in self.consignments}) != len(self.consignments):
            raise ValueError("Consignment IDs must be distinct")
        if self.timeCostPerHour is not None and not self.timeCostBasis:
            raise ValueError("A time-cost declaration requires a basis")
        return self


class Sampling(Strict):
    seed: int = Field(ge=0, le=2**53 - 1)
    minPower: int = Field(default=6, ge=3, le=12)
    maxPower: int = Field(default=11, ge=3, le=13)
    scrambles: int = Field(default=8, ge=4, le=16)
    standardErrorThreshold: float = Field(default=25, gt=0, le=1e7)

    @model_validator(mode="after")
    def powers(self):
        if self.maxPower < self.minPower:
            raise ValueError("Maximum Sobol power must be at least the minimum")
        if (2**self.maxPower) * self.scrambles > 65_536:
            raise ValueError("The bounded study supports at most 65,536 futures")
        return self


@dataclass(frozen=True)
class Futures:
    uniforms: FloatArray
    closure_hours: FloatArray
    handling_hours: FloatArray
    fuel_price: FloatArray | None
    fx: dict[str, FloatArray]
    scrambles: int

    @property
    def samples(self):
        return len(self.closure_hours)


@dataclass(frozen=True)
class OptionLoss:
    option: RiskOption
    arrival: FloatArray
    costs: CostBreakdown
    consignments: list[ConsignmentLoss]
    priority_miss: np.ndarray | None


def triangular_icdf(u: FloatArray, low: float, mode: float, high: float) -> FloatArray:
    if low == high:
        return np.full(u.shape, low)
    split = (mode - low) / (high - low)
    return np.where(u < split, low + np.sqrt(u * (high - low) * (mode - low)),
                    high - np.sqrt((1 - u) * (high - low) * (high - mode)))


def handling_icdf(u: FloatArray, distribution: DelayDistribution) -> FloatArray:
    if distribution.kind == "TRIANGULAR":
        return triangular_icdf(u, distribution.minimum, distribution.mode, distribution.maximum)
    cdf = np.cumsum(distribution.weights)
    indices = np.minimum(np.searchsorted(cdf, u, side="right"), len(cdf) - 1)
    return np.asarray(distribution.values)[indices]


def closure_icdf(u: FloatArray, closure: ClosureBasis) -> FloatArray:
    p = closure.fizzleProbability
    if closure.medianHours == 0 or p == 1:
        return np.zeros_like(u)
    conditional = np.clip((u - p) / (1 - p), 1e-12, 1 - 1e-12)
    duration = np.maximum(2, closure.medianHours * np.exp(closure.logSigma * ndtri(conditional)))
    return np.where(u < p, 0, duration)


def map_futures(study: RiskStudy, uniforms: FloatArray) -> Futures:
    """Input shape [independent replicate, future within replicate, variate]."""
    if uniforms.ndim != 3 or uniforms.shape[-1] != DIMENSIONS:
        raise ValueError("Expected a replicate × future × variate array")
    z = ndtri(np.clip(uniforms.reshape(-1, DIMENSIONS), 1e-12, 1 - 1e-12))
    z[:, 2] = .20 * z[:, 0] + .35 * z[:, 1] + np.sqrt(1 - .20**2 - .35**2) * z[:, 2]
    z[:, 3] = .40 * z[:, 2] + np.sqrt(1 - .40**2) * z[:, 3]
    z[:, 5] = .20 * z[:, 4] + np.sqrt(1 - .20**2) * z[:, 5]
    u = ndtr(z)
    fx = {}
    if study.fx:
        quotes = study.fx.datedQuotes
        idx = np.minimum(np.floor(u[:, 5] * len(quotes)).astype(int), len(quotes) - 1)
        reporting = [row.get(study.reportingCurrency) for row in quotes]
        if all(rate is not None for rate in reporting):
            for currency in quotes[0]:
                fx[currency] = (np.asarray(reporting) / np.asarray([row[currency] for row in quotes]))[idx]
    fuel = study.fuel
    return Futures(
        u, closure_icdf(u[:, 0], study.closure), handling_icdf(u[:, 3], study.handling),
        None if fuel is None else fuel.low + (fuel.high - fuel.low) * u[:, 4], fx, uniforms.shape[0],
    )


def worlds_for(config: Sampling, power: int, *, method: Literal["sobol", "random"] = "sobol",
               stream: int = 0) -> FloatArray:
    seeds = np.random.SeedSequence([config.seed, stream]).spawn(config.scrambles)
    engines = [np.random.default_rng(seed) for seed in seeds]
    if method == "random":
        return np.stack([engine.random((2**power, DIMENSIONS)) for engine in engines])
    # Draw complete base-two prefixes. Calling this at successive powers preserves every point.
    return np.stack([qmc.Sobol(DIMENSIONS, scramble=True, seed=engine).random_base2(power) for engine in engines])


def sample_losses(study: RiskStudy, option: RiskOption, futures: Futures, *,
                  closure_hours: FloatArray | None = None, wait_hours: float = 0) -> OptionLoss:
    u = futures.uniforms
    duration = futures.closure_hours if closure_hours is None else closure_hours
    start = study.closure.startedHour
    reopen = start + duration
    closure_wait = np.zeros(futures.samples)
    if option.reachClosureHour is not None and option.reachClosureHour >= 0:
        closure_wait = queue_wait_hours(option.reachClosureHour + wait_hours, start, reopen,
                                        reopen + duration * study.closure.drainFraction)
    if option.weather:
        wx = option.weather
        indices = np.minimum((u[:, 1] * len(wx.windKn)).astype(int), len(wx.windKn) - 1)
        wind = np.asarray(wx.windKn)[indices]
        weather = np.maximum(wind - wx.thresholdKnots, 0) * wx.delayHoursPerExcessKnot
    else:
        weather = triangular_icdf(u[:, 1], 0, 2, 6)
    if option.port:
        low, median, high = option.port.congestion
        congestion = np.interp(u[:, 2], [0, .1, .5, .9, 1], [low, low, median, high, high])
        berth = np.maximum(option.port.medianWaitHours + (congestion - median) * option.port.waitHoursPerIndexPoint, 0)
    else:
        berth = np.interp(u[:, 2], [0, .1, .5, .9, 1], [0, 0, 3, 12, 12])
    berth *= option.berthExposure
    handling = futures.handling_hours * option.handlingExposure
    arrival = option.cleanDeliveryHours + closure_wait + weather * option.weatherExposure + berth + handling + wait_hours
    state = CostState(
        arrival, study.plannedDeliveryHours,
        None if option.dwellHours is None else option.dwellHours + berth + handling,
        None if option.detentionHours is None else option.detentionHours + handling,
        None if option.unpoweredHours is None else option.unpoweredHours + handling,
        option.areas, u[:, 6], u[:, 7], futures.fx,
    )
    cargo = []
    for shipment in study.consignments:
        offset = float(shipment.deliveryOffsetHours or 0)
        delivery = replace(state, arrival_hours=arrival + offset,
                           planned_arrival_hours=state.planned_arrival_hours + offset) if offset else state
        cargo.append(evaluate_consignment(shipment, delivery, study.at, study.reportingCurrency))
    components, missing, basis = {}, {}, {}
    if option.fixedVoyageCost is not None:
        components["fixed"] = np.full(futures.samples, option.fixedVoyageCost)
        basis["fixed"] = (option.source,)
    if study.timeCostPerHour is not None:
        components["time_cost"] = np.maximum(arrival - study.plannedDeliveryHours, 0) * study.timeCostPerHour
        basis["time_cost"] = (study.timeCostBasis,)
    if option.fuelTonnes is not None or study.fuel is not None:
        if option.fuelTonnes is None or study.fuel is None:
            missing["fuel"] = "Option fuel or declared fuel-price range unavailable"
        else:
            currency = study.fuel.currency
            rate = 1 if currency == study.reportingCurrency else futures.fx.get(currency)
            if rate is None:
                missing["fuel"] = f"No {currency}/{study.reportingCurrency} FX basis"
            else:
                components["fuel"] = option.fuelTonnes * futures.fuel_price * rate
                basis["fuel"] = (option.source, study.fuel.source)
    cargo_costs = combine_costs({row.consignment_id: row.costs for row in cargo}, futures.samples)
    costs = combine_costs({
        "cargo": cargo_costs, "voyage": CostBreakdown(futures.samples, components, missing, basis),
    }, futures.samples)
    priority = [row.on_time for row in cargo if row.priority == 1]
    miss = None if any(row.priority is None for row in cargo) or any(row is None for row in priority) else (
        np.logical_not(np.logical_and.reduce(priority)) if priority else np.zeros(futures.samples, dtype=bool)
    )
    return OptionLoss(option, arrival, costs, cargo, miss)


def comparable(losses: list[OptionLoss]) -> bool:
    if not losses or any(row.costs.known_subtotal is None for row in losses):
        return False
    scopes = {(tuple(sorted(row.costs.components)), tuple(sorted(row.costs.unknown))) for row in losses}
    return len(scopes) == 1


def replicate_ci(values: FloatArray, scrambles: int, statistic=np.mean) -> dict:
    grouped = values.reshape(scrambles, -1)
    estimates = np.array([statistic(row) for row in grouped])
    estimate = float(statistic(values))
    se = float(estimates.std(ddof=1) / np.sqrt(scrambles))
    width = float(t.ppf(.975, scrambles - 1) * se)
    return {"estimate": estimate, "standardError": se, "lower95": estimate - width, "upper95": estimate + width}


def _probability(values: np.ndarray | None, scrambles: int) -> dict | None:
    if values is None:
        return None
    interval = replicate_ci(values, scrambles)
    interval["lower95"] = max(0, interval["lower95"])
    interval["upper95"] = min(1, interval["upper95"])
    return interval


def _quantiles(values, probabilities):
    return [float(value) for value in np.quantile(values, probabilities)]


def public_losses(rows: list[OptionLoss], futures: Futures) -> list[dict]:
    comparable_scope = comparable(rows)
    best = np.minimum.reduce([row.costs.known_subtotal for row in rows]) if comparable_scope else None
    baseline = rows[0]
    published = []
    for row in rows:
        subtotal = row.costs.known_subtotal
        uncertainty = None if subtotal is None else {
            "mean": replicate_ci(subtotal, futures.scrambles),
            "cvar95": replicate_ci(subtotal, futures.scrambles, cvar),
        }
        unknown = row.costs.unknown
        cargo = []
        for consignment in row.consignments:
            components = consignment.costs.components
            keep = next(item for item in baseline.consignments if item.consignment_id == consignment.consignment_id)
            paired = (consignment.costs.known_subtotal - keep.costs.known_subtotal
                      if set(components) == set(keep.costs.components) and components else None)
            cargo.append({
                "id": consignment.consignment_id, "priority": consignment.priority,
                "onTime": _probability(consignment.on_time, futures.scrambles), "deadlineBasis": consignment.deadline_basis,
                "spoilage": _probability(consignment.spoilage, futures.scrambles),
                "insuredValue": consignment.insured_value.model_dump(mode="json") if consignment.insured_value else None,
                "excludedAreas": consignment.excluded_areas, "unknown": consignment.costs.unknown,
                "expectedExtraCost": None if paired is None else replicate_ci(paired, futures.scrambles),
                "drivers": {key: {"expected": float(samples.mean()), "basis": consignment.costs.basis[key]}
                            for key, samples in components.items()},
            })
        published.append({
            "id": row.option.id, "label": row.option.label, "action": row.option.action,
            "arrival": {"probabilities": [.1, .5, .9], "hours": _quantiles(row.arrival, [.1, .5, .9]),
                        "mean": replicate_ci(row.arrival, futures.scrambles)},
            "cost": {**summarize_cost(row.costs), "uncertainty": uncertainty,
                     "dots": [] if subtotal is None else _quantiles(subtotal, np.linspace(0, 1, 21))},
            "priorityMiss": _probability(row.priority_miss, futures.scrambles),
            "regret": None if best is None else {
                "scope": "known subtotal" if unknown else "complete declared cost",
                "mean": replicate_ci(subtotal - best, futures.scrambles),
                "quantiles": _quantiles(subtotal - best, [.1, .5, .9]),
            },
            "consignments": cargo,
        })
    return published


def adaptive(study: RiskStudy, config: Sampling, *, progress=None) -> tuple[list[OptionLoss], Futures, dict]:
    previous = None
    diagnostics = []
    order = sorted(study.options, key=lambda option: (option.id != study.keepOptionId, option.id))
    for power in range(config.minPower, config.maxPower + 1):
        futures = map_futures(study, worlds_for(config, power))
        rows = [sample_losses(study, option, futures) for option in order]
        ranked = sorted(rows, key=lambda row: float(row.costs.known_subtotal.mean())) if comparable(rows) else []
        pair = tuple(row.option.id for row in ranked[:2]) if len(ranked) >= 2 else None
        paired = None if pair is None else replicate_ci(
            ranked[1].costs.known_subtotal - ranked[0].costs.known_subtotal, config.scrambles,
        )
        stable = pair is not None and pair == previous
        converged = bool(stable and paired["standardError"] <= config.standardErrorThreshold)
        stage = {
            "n": futures.samples, "perScramble": 2**power, "topTwo": pair,
            "stable": stable, "difference": paired, "converged": converged,
            "knownCostEstimates": {
                row.option.id: float(row.costs.known_subtotal.mean())
                for row in rows if row.costs.known_subtotal is not None
            },
        }
        diagnostics.append(stage)
        if progress is not None:
            progress(stage)
        if converged or pair is None:
            break
        previous = pair
    return rows, futures, {
        **stage, "scrambles": config.scrambles, "threshold": config.standardErrorThreshold,
        "stages": diagnostics, "stop": "converged" if converged else "no comparable pair" if pair is None else "maximum N",
    }


def input_key(study: RiskStudy, config: Sampling) -> str:
    return digest({"version": VERSION, "study": study.model_dump(mode="json"),
                   "sampling": config.model_dump(mode="json", exclude={"seed"})})


def calculate(study: RiskStudy, config: Sampling, *, progress=None, policy=None, sensitivity=False) -> dict:
    rows, futures, diagnostics = adaptive(study, config, progress=progress)
    report = {
        "version": VERSION, "problemId": study.problemId, "inputHash": input_key(study, config), "seed": config.seed,
        "sampleHash": digest(futures.uniforms.tolist()), "scope": study.scope, "currency": study.reportingCurrency,
        "asOf": study.at.isoformat(), "keepOptionId": study.keepOptionId, "diagnostics": diagnostics,
        "commonRandomNumbers": True, "dependence": DESIGN,
        "sourceBasis": {"closure": study.closure.source, "handling": study.handling.declaration,
                        "fuel": study.fuel.source if study.fuel else None, "fx": study.fx.source if study.fx else None,
                        "options": {option.id: {"passage": option.source,
                            "weather": option.weather.source + " · assumed wind-to-delay conversion" if option.weather else FALLBACK,
                            "port": option.port.source if option.port else "ASSUMPTION · berth wait quantiles 0/3/12 h"}
                                    for option in study.options}},
        "options": public_losses(rows, futures),
    }
    if policy is not None:
        from .cargo_policy import closure_sweep, decide
        report["decision"] = decide(study, rows, futures, policy)
        if sensitivity:
            report["closureSensitivity"] = closure_sweep(study, config, policy)
    return report


@lru_cache(maxsize=24)
def _cached(study_json: str, config_json: str) -> str:
    result = calculate(RiskStudy.model_validate_json(study_json), Sampling.model_validate_json(config_json))
    return json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)


def study_bytes(study: RiskStudy, config: Sampling) -> bytes:
    def canonical(value):
        return json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False)

    return _cached(canonical(study), canonical(config)).encode()


def company_rollup(choices: dict[str, tuple[RiskStudy, str]], config: Sampling, *, power: int) -> dict:
    """Evaluate a declared multi-voyage portfolio on one joint latent draw."""
    if not choices or not config.minPower <= power <= config.maxPower:
        raise ValueError("A nonempty portfolio and a power within the declared budget are required")
    clocks = {(study.at, study.reportingCurrency) for study, _ in choices.values()}
    if len(clocks) != 1:
        raise ValueError("Company rollups require one as-of instant and reporting currency")
    uniforms = worlds_for(config, power)
    rows = {}
    for voyage, (study, option_id) in sorted(choices.items()):
        option = next((row for row in study.options if row.id == option_id), None)
        if option is None:
            raise ValueError(f"Unknown eligible option for voyage {voyage}")
        rows[voyage] = sample_losses(study, option, map_futures(study, uniforms))
    count = config.scrambles * 2**power
    total = combine_costs({voyage: row.costs for voyage, row in rows.items()}, count)
    subtotal = total.known_subtotal
    return {
        "n": count, "currency": next(iter(clocks))[1], "cost": summarize_cost(total),
        "numericalUncertainty": None if subtotal is None else {
            "knownMean": replicate_ci(subtotal, config.scrambles),
            "knownCvar95": replicate_ci(subtotal, config.scrambles, cvar),
        },
        "missByVoyage": {voyage: {item.consignment_id: _probability(
            None if item.on_time is None else ~item.on_time, config.scrambles,
        ) for item in row.consignments} for voyage, row in rows.items()},
        "dependence": "One common latent weather, closure, port, handling and market draw per sampled future",
        "seed": config.seed, "sampleHash": digest(uniforms.tolist()),
    }
