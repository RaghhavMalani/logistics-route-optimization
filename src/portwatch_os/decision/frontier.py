"""Multi-objective comparison: the Pareto frontier, the labelled picks, and
one deliberately explicit ranking.

The temptation in a decision product is to add everything up into a score and
sort by it. The score then hides the trade-off that *was* the decision: the
cheap option is slow, the fast option is exposed, and the number that ranked
them says neither. So comparison happens in three layers, each visible:

1.  **Dominance.** An option is dominated if another feasible option is no
    worse on every selected objective and strictly better on at least one.
    That is a fact about the numbers, not a preference, and it needs no
    weights. Dominated options are kept and labelled with what dominates them.
2.  **Labelled picks.** FASTEST, LOWEST RISK, LOWEST FUEL, LOWEST COST,
    BEST SCHEDULE RELIABILITY -- each the best feasible option on one measured
    objective. A label whose objective is not measured is absent rather than
    filled in.
3.  **A ranking with its weights on the outside.** BALANCED is a weighted sum
    over normalised objectives, and the weights, the normalisation and the
    objectives that had to be dropped because some option could not be measured
    on them are all returned with the answer. It is a stated preference an
    operator can disagree with, not a hidden one.

Options whose measure on a selected objective is unknown are *incomparable* on
that objective. They are excluded from dominance over it rather than treated
as best or worst -- an unknown is not a zero -- and the frontier says which
objectives kept them out.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.decision.model import (
    CARGO_CONNECTION,
    DecisionFrontier,
    DecisionObjective,
    DecisionOption,
    MAXIMISE,
    MINIMISE,
    OBJECTIVES,
    PORT_AUTHORITY,
    PORT_BERTHING,
    SHIPPING_COMPANY,
    TERMINAL_OPERATOR,
    VESSEL_OPERATOR,
    VESSEL_ROUTING,
)

#: The picks a UI may show, and the objective each reads. ``BEST_SCHEDULE_
#: RELIABILITY`` reads the option's uncertainty, which is the weakest
#: confidence in its evaluation -- the option whose numbers are most likely to
#: hold.
PICKS: Dict[str, str] = {
    "FASTEST": "eta",
    "LOWEST_RISK": "risk",
    "LOWEST_FUEL": "fuel",
    "LOWEST_COST": "cost",
    "BEST_SCHEDULE_RELIABILITY": "uncertainty",
    "LOWEST_WEATHER": "weather",
    "SHORTEST_WAIT": "port_wait",
    "FEWEST_MISSED_DEPARTURES": "missed_departures",
    "EARLIEST_SAILING": "sailing",
    "MOST_SLACK": "slack",
}

#: Explicit preference weights by domain. Stated once, returned with every
#: ranking, and deliberately coarse: an operator can hold "risk counts about
#: a third, time a quarter" in their head, which is the point.
WEIGHTS: Dict[str, Dict[str, float]] = {
    VESSEL_ROUTING: {
        "risk": 0.35, "eta": 0.25, "fuel": 0.15, "weather": 0.10,
        "cost": 0.10, "uncertainty": 0.05,
    },
    # A missed departure is a broken commitment, and the twin's own reward
    # charges it at twenty-five wait-hours; the weights say the same thing.
    PORT_BERTHING: {
        "missed_departures": 0.40, "port_wait": 0.25, "turnaround": 0.10,
        "berth_utilisation": 0.10, "yard_pressure": 0.05, "crane_utilisation": 0.10,
    },
    CARGO_CONNECTION: {
        "sailing": 0.30, "slack": 0.25, "dwell": 0.20, "handling": 0.10,
        "cost": 0.10, "uncertainty": 0.05,
    },
}


def _value(option: DecisionOption, key: str) -> Optional[float]:
    measure = option.measure(key)
    return None if measure is None or not measure.available else measure.value


def dominates(
    a: DecisionOption,
    b: DecisionOption,
    objectives: Sequence[DecisionObjective],
) -> bool:
    """Whether ``a`` dominates ``b``: no worse everywhere, better somewhere.

    Requires both to be measured on every objective; an unknown on either side
    makes the pair incomparable and the answer is ``False`` in both directions.
    """
    better_somewhere = False
    for objective in objectives:
        va, vb = _value(a, objective.key), _value(b, objective.key)
        if va is None or vb is None:
            return False
        if objective.better(vb, va):
            return False
        if objective.better(va, vb):
            better_somewhere = True
    return better_somewhere


def pareto(
    options: Sequence[DecisionOption],
    objectives: Sequence[DecisionObjective],
) -> DecisionFrontier:
    """The nondominated feasible options over the selected objectives."""
    feasible = [o for o in options if o.feasible and o.evaluation is not None]
    incomparable: Dict[str, List[str]] = {}
    comparable: List[DecisionOption] = []
    for option in feasible:
        missing = [obj.key for obj in objectives if _value(option, obj.key) is None]
        if missing:
            incomparable[option.option_id] = missing
        else:
            comparable.append(option)

    dominated: Dict[str, str] = {}
    for option in comparable:
        for other in comparable:
            if other is option:
                continue
            if dominates(other, option, objectives):
                dominated[option.option_id] = other.option_id
                break

    nondominated = [o.option_id for o in comparable if o.option_id not in dominated]
    return DecisionFrontier(
        objectives=[obj.key for obj in objectives],
        nondominated=nondominated,
        dominated=dominated,
        incomparable=incomparable,
        picks=picks(feasible),
    )


def picks(options: Sequence[DecisionOption]) -> Dict[str, str]:
    """The best feasible option on each measured objective, by label."""
    out: Dict[str, str] = {}
    for label, key in PICKS.items():
        objective = OBJECTIVES[key]
        measured = [(o, _value(o, key)) for o in options if _value(o, key) is not None]
        if not measured:
            continue
        best = min(measured, key=lambda pair: pair[1]) if objective.direction == MINIMISE \
            else max(measured, key=lambda pair: pair[1])
        out[label] = best[0].option_id
    return out


def rank(
    options: Sequence[DecisionOption],
    domain: str,
    *,
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """BALANCED: a weighted sum over normalised objectives, with its workings.

    Normalisation is min-max across the feasible options on each objective,
    oriented so 0 is best and 1 is worst. An objective that any feasible
    option cannot be measured on is dropped for *all* of them and reported as
    dropped: ranking two options on cost when a third has no cost basis would
    quietly favour whichever happened to be priced.
    """
    chosen = dict(weights or WEIGHTS.get(domain, {}))
    feasible = [o for o in options if o.feasible and o.evaluation is not None]
    if not feasible:
        return {"order": [], "weights": chosen, "objectivesUsed": [], "objectivesDropped": {},
                "scores": {}, "note": "no feasible option to rank"}

    used: Dict[str, float] = {}
    dropped: Dict[str, str] = {}
    for key, weight in chosen.items():
        values = [_value(o, key) for o in feasible]
        if any(v is None for v in values):
            missing = [o.option_id for o, v in zip(feasible, values) if v is None]
            dropped[key] = f"not measured for {', '.join(missing)}"
            continue
        used[key] = weight

    total_weight = sum(used.values())
    scores: Dict[str, Dict[str, Any]] = {}
    for option in feasible:
        terms: Dict[str, float] = {}
        for key, weight in used.items():
            objective = OBJECTIVES[key]
            values = [_value(o, key) for o in feasible]
            low, high = min(values), max(values)  # type: ignore[type-var]
            value = _value(option, key)
            if high == low:
                normalised = 0.0
            else:
                normalised = (value - low) / (high - low)  # type: ignore[operator]
                if objective.direction == MAXIMISE:
                    normalised = 1.0 - normalised
            terms[key] = round(normalised * (weight / total_weight), 4) if total_weight else 0.0
        scores[option.option_id] = {"score": round(sum(terms.values()), 4), "terms": terms}

    order = sorted(
        scores,
        # Ties break toward the baseline, then by id: a change that is not
        # measurably better than doing nothing is not recommended over it.
        key=lambda oid: (scores[oid]["score"], 0 if _is_baseline(feasible, oid) else 1, oid),
    )
    return {
        "order": order,
        "weights": chosen,
        "objectivesUsed": list(used),
        "objectivesDropped": dropped,
        "scores": scores,
        "method": "weighted sum of min-max normalised objectives (0 best, 1 worst)",
    }


def _is_baseline(options: Sequence[DecisionOption], option_id: str) -> bool:
    return any(o.option_id == option_id and o.is_baseline for o in options)


def against_baseline(
    option: DecisionOption,
    baseline: Optional[DecisionOption],
    objectives: Sequence[DecisionObjective],
) -> Dict[str, Dict[str, Any]]:
    """Objective by objective: this option, the baseline, and the difference."""
    out: Dict[str, Dict[str, Any]] = {}
    for objective in objectives:
        mine = option.measure(objective.key)
        theirs = None if baseline is None else baseline.measure(objective.key)
        a = None if mine is None or not mine.available else mine.value
        b = None if theirs is None or not theirs.available else theirs.value
        entry: Dict[str, Any] = {
            "unit": objective.unit,
            "option": None if a is None else round(a, 4),
            "baseline": None if b is None else round(b, 4),
            "delta": None if a is None or b is None else round(a - b, 4),
            "better": None if a is None or b is None else (
                objective.better(a, b) if a != b else None
            ),
        }
        if a is None:
            entry["unknownBecause"] = None if mine is None else mine.unknown_because
        out[objective.key] = entry
    return out


__all__ = ["PICKS", "WEIGHTS", "against_baseline", "dominates", "pareto", "picks", "rank"]
