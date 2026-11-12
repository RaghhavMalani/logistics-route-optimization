"""Paper corpora. Generation and scoring are separate from option selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from time import perf_counter

import numpy as np

from src.portwatch_os.cargo.demo_consignments import assumption, demo_consignments, usd
from src.portwatch_os.world.branch import ObservedWorldState
from src.portwatch_os.world.build import build_world, seed_for
from src.portwatch_os.world.graph import EVENT, key
from src.portwatch_os.world.live import Revision

from . import benchmark as legacy
from .actions import CHANGE_DESTINATION_PORT, REROUTE, SPEED_UP
from .cargo_policy import RuleSettings, decide
from .cargo_sampling import RiskOption, RiskStudy, Sampling, adaptive, map_futures, sample_losses
from .commercial import instant
from .engine import DecisionEngine
from .model import DecisionActor, SHIPPING_COMPANY
from .outcome import option_derived

PAPER_SEED = 20261112
CORPUS_OFFSET = 100_000
TIME_PRICE = 250.0
TUNING_Q = (.50, .55, .60, .65, .70, .75, .80, .90)
TUNING_EPSILON = (.10, .20, .35, .50, .75, 1.0)
DOMAINS = ("vessel", "cargo")
BASELINE_POLICIES = ("current_plan", "heuristic", "portwatch_balanced", "portwatch_robust")
POLICIES = (*BASELINE_POLICIES, "R1", "R2", "R3", "R4", "R5", "time_only")
INCUMBENT = "portwatch_robust"


@dataclass(frozen=True)
class Case:
    id: str
    domain: str
    seed: int
    study: RiskStudy
    legacy_choices: dict[str, tuple[str | None, float, str]]
    realised: dict[str, tuple[float, float]]
    labels: dict
    build_ms: float


def sampling(seed: int, case_seed: int, *, smoke: bool = False) -> Sampling:
    derived = int(np.random.SeedSequence([seed, case_seed, 413]).generate_state(1)[0])
    return Sampling(seed=derived, scrambles=4, minPower=3 if smoke else 6, maxPower=4 if smoke else 9,
                    standardErrorThreshold=250)


def _option(option, *, clean: float, cargo: bool) -> RiskOption | None:
    if not option.feasible:
        return None
    derived = option_derived(option)
    hours = derived.get("hoursToChokepoint")
    if option.action == CHANGE_DESTINATION_PORT:
        # The original option has no onward delivery clock to the booked destination.
        return None
    bypass = option.action in {REROUTE, SPEED_UP}
    hold = float(derived.get("holdHours") or 0)
    if bypass:
        eta = option.measure("eta")
        if eta is None or not eta.available:
            return None
        hours, hold = None, float(eta.value)
    elif hours is None:
        return None
    return RiskOption(
        id=option.option_id, label=option.label, action=option.action,
        cleanDeliveryHours=max(0, clean + hold), reachClosureHour=hours,
        areas=() if bypass else ("RED_SEA",),
        weatherExposure=1 if cargo else 0,
        berthExposure=1 if cargo else 0,
        handlingExposure=(.6 if option.action == REROUTE else 1) if cargo else 0,
        dwellHours=14 if cargo else None, detentionHours=18 if cargo else None,
        unpoweredHours=(1 if option.action == REROUTE else 2) if cargo else None,
        fuelTonnes=(60 + max(0, hold) * .08) if cargo else None,
        latestStartHour=option.provenance.get("closesInHours"),
        source="ASSUMPTION · synthetic cargo projection over the existing feasible routing option"
               if cargo else "Existing frozen vessel benchmark routing option",
    )


def cargo_mix(at, planned: float, seed: int, family: str | None = None) -> tuple[list[dict], str]:
    rng = np.random.default_rng(np.random.SeedSequence([seed, 301]))
    family = family or ("reefer", "deadline", "war", "bulk")[int(rng.integers(0, 4))]
    pool = [item for rows in demo_consignments(at).values() for item in rows]
    selections = {
        "reefer": (0, 3, 4, 6),
        "deadline": (1, 1, 5, 2),
        "war": (5, 7, 1, 8),
        "bulk": (2, 8, 1, 7),
    }[family]
    cargo = []
    for index, selected in enumerate(selections, 1):
        row = pool[selected]
        # Isolate each declaration even when a family uses two copies of a template.
        terms = dict(row["riskTerms"])
        value = int(rng.uniform(15_000, 95_000) * (5 if family == "war" else 1))
        if family == "bulk":
            value = max(2_000, value // 10)
        due = at + timedelta(hours=planned + float(rng.uniform(12, 140)))
        terms.update(
            cifValue=assumption(usd(value)), insuredValue=None,
            deliveryDeadline=assumption(due),
            priority=assumption(1 if index <= 2 and family in ("reefer", "deadline") else 2 if index < 4 else 3),
            latePenalty=assumption({"amount": usd(int(rng.uniform(500, 24_000)) if family == "deadline" else 380),
                                    "unit": "per_day"}),
            generalAverageExposed=assumption(False),
            warRiskAreas=assumption([{"area": "RED_SEA", "required": assumption(True),
                "premiumRate": assumption(str(round(float(rng.uniform(.025, .10)), 5)) if family == "war" else "0.003")}]),
        )
        if terms["handlingClass"]["value"] == "reefer":
            terms["remainingShelfLifeHours"] = assumption(planned + float(rng.uniform(25, 185)))
            terms["maxUnpoweredHours"] = assumption(float(rng.uniform(4, 9)))
        cargo.append(row | {"id": f"CASE-CARGO-{index:02d}", "deadline": due, "riskTerms": terms})
    return cargo, family


def generate(domain: str, seed: int, master: int, engine: DecisionEngine) -> Case:
    if domain not in DOMAINS:
        raise ValueError(f"Unknown paper domain {domain}")
    cargo = domain == "cargo"
    case_seed = seed + CORPUS_OFFSET if cargo else seed
    event, subject, truth, _ = legacy._vessel_case(case_seed)
    at = legacy.NOW
    graph = build_world(events=[event], voyages=[subject], now=at)
    state = ObservedWorldState(state_id=f"bm-{case_seed}", revision=Revision("DEMO", None, "e", "f", 1),
                               at=at, graph=graph, traffic_mode="SIMULATED_TRAFFIC")
    started = perf_counter()
    problem = engine.solve_vessel(
        state, event_key=key(EVENT, event.event_id), seed=seed_for(event), vessel_id=subject.vessel_id,
        actor=DecisionActor(SHIPPING_COMPANY), at=at, decision_id=f"bm-vsl-{case_seed}",
    )
    build_ms = (perf_counter() - started) * 1000
    clean = 180.0
    options = tuple(row for option in problem.options if (row := _option(option, clean=clean, cargo=cargo)) is not None)
    if problem.baseline_option_id not in {row.id for row in options}:
        raise ValueError("No baseline routing with a modelled delivery clock")
    declarations, family = cargo_mix(at, clean, int(np.random.SeedSequence([master, case_seed, 620]).generate_state(1)[0])) if cargo else ([], "vessel")
    study = RiskStudy(
        problemId=f"{domain}-{seed}", at=at, reportingCurrency="USD", keepOptionId=problem.baseline_option_id,
        plannedDeliveryHours=clean, options=options, consignments=declarations,
        closure={
            "startedHour": (instant(event.first_seen) - at).total_seconds() / 3600,
            "medianHours": 12 + 150 * event.severity**2, "logSigma": .55,
            "fizzleProbability": .5 * (1 - event.confidence),
            "source": "ASSUMPTION · frozen vessel benchmark lognormal and fizzle model",
        },
        handling={"kind": "TRIANGULAR", "minimum": 0, "mode": 1.2, "maximum": 5,
                  "declaration": "ASSUMPTION · synthetic downstream handling shift, hours"},
        fuel={"low": 450, "high": 650, "currency": "USD",
              "source": "ASSUMPTION · synthetic USD/tonne band"} if cargo else None,
        timeCostPerHour=TIME_PRICE if not cargo else None,
        timeCostBasis="ASSUMPTION · USD 250 per positive vessel-delay hour (proxy)" if not cargo else None,
        scope="SYNTHETIC CARGO · conditional study" if cargo else "FROZEN VESSEL BENCHMARK · illustrative USD delay proxy",
    )
    picks = legacy._vessel_policies(problem, event)
    # Preserve the incumbent's contingent WAIT scoring from the original benchmark.
    picks[INCUMBENT] = legacy._robust_pick(problem, truth=truth)
    if cargo:
        rng = np.random.default_rng(np.random.SeedSequence([master, case_seed, 1009]))
        duration = truth["closureHours"]
        drain = truth["backlogDrainHours"] / duration if duration else 0
        hidden = study.model_copy(update={"closure": study.closure.model_copy(update={"drainFraction": drain})})
        world = map_futures(hidden, rng.random((1, 1, 8)))
        realised = {}
        for option in options:
            row = sample_losses(hidden, option, world, closure_hours=np.array([duration]))
            if row.costs.total is not None:
                realised[option.id] = (float(row.arrival[0] - clean), float(row.costs.total[0]))
    else:
        # Include every scoreable incumbent option in the oracle, including any
        # landing-only alternative supported by the original vessel scorecard.
        realised = {oid: (row["delay"], row["delay"] * TIME_PRICE)
                    for oid, row in legacy._vessel_realised(problem, truth).items() if row["feasible"]}
    return Case(study.problemId, domain, seed, study, picks, realised, {"family": family, "caseSeed": case_seed}, build_ms)


def cases(split: str, domain: str, master: int, *, smoke: bool = False):
    first, count = legacy.CORPORA[split]
    engine = DecisionEngine(capacity=64)
    for seed in range(first, first + (2 if smoke else count)):
        try:
            yield generate(domain, seed, master, engine), None
        except (ValueError, KeyError) as exc:
            yield None, {"id": f"{domain}-{seed}", "domain": domain, "split": split,
                         "error": f"{type(exc).__name__}: {exc}"}


def score(case: Case, name: str, choice: str | None, decision_ms: float) -> dict:
    result = case.realised.get(choice) if choice else None
    keep = case.realised.get(case.study.keepOptionId)
    measure = 0 if case.domain == "vessel" else 1
    best_h = min((row[0] for row in case.realised.values()), default=None)
    best_c = min((row[1] for row in case.realised.values()), default=None)
    best = best_h if measure == 0 else best_c
    act_best = keep is not None and best is not None and best < keep[measure] - 1e-9
    acted = choice is not None and choice != case.study.keepOptionId
    return {
        "case": case.id, "domain": case.domain, "seed": case.seed, "family": case.labels["family"],
        "policy": name, "choice": choice, "scored": result is not None,
        "hoursRegret": None if result is None else max(0, result[0] - best_h),
        "costRegret": None if result is None else max(0, result[1] - best_c),
        "cost": None if result is None else result[1], "hours": None if result is None else result[0],
        "actIsBest": act_best, "acted": acted,
        "captured": bool(act_best and acted and result is not None and result[measure] < keep[measure] - 1e-9),
        "unnecessary": None if not acted or result is None or keep is None else result[measure] >= keep[measure] - 1e-9,
        "decisionMs": decision_ms,
    }


def prepared(case: Case, master: int, *, smoke: bool = False):
    started = perf_counter()
    rows, futures, _ = adaptive(case.study, sampling(master, case.labels["caseSeed"], smoke=smoke))
    return rows, futures, (perf_counter() - started) * 1000


def evaluate(case: Case, master: int, q: float, epsilon: float, *, smoke: bool = False) -> list[dict]:
    rows, worlds, simulation_ms = prepared(case, master, smoke=smoke)
    scored = [score(case, name, case.legacy_choices[name][0], case.legacy_choices[name][1] +
                    (case.build_ms if name in {"portwatch_balanced", "portwatch_robust"} else 0))
              for name in BASELINE_POLICIES]
    for rule in ("R1", "R2", "R3", "R4", "R5"):
        started = perf_counter()
        result = decide(case.study, rows, worlds, RuleSettings(rule=rule, q=q, epsilon=epsilon))
        scored.append(score(case, rule, result["optionId"], case.build_ms + simulation_ms +
                            (perf_counter() - started) * 1000))
    started = perf_counter()
    time_pick = min(rows, key=lambda row: (row.arrival.mean(), row.option.id != case.study.keepOptionId, row.option.id))
    scored.append(score(case, "time_only", time_pick.option.id, case.build_ms + simulation_ms +
                        (perf_counter() - started) * 1000))
    return scored
