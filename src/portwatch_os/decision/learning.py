"""Decision learning: did the recommendation help, measured after the fact.

Predicting is cheap; the question that decides whether a decision engine is
worth trusting is answered only once outcomes arrive:

    Predicted:  option A saves 7.2 h
    Actual:     saved 4.9 h

Everything here reads the ledger's :class:`DecisionProblemRecord` rows --
the problem *as computed*, the human choice, the action taken, the observed
outcome -- and computes from them alone. Nothing is recomputed against the
world as it turned out; a scoring pass that re-ran the engine with hindsight
would grade a decision nobody could have made.

What is tracked, per resolved problem and in aggregate:

*   **prediction error** -- observed minus predicted, per objective, for the
    option that was actually taken;
*   **ranking accuracy** -- whether the recommended option was the best once
    the outcome of every option is known (a mission reveals all of them; a
    live decision reveals only the one taken, and says so);
*   **regret** -- the realised objective of the option taken against the
    realised best, where the counterfactuals are known;
*   **calibration** -- absolute error bucketed by the confidence the engine
    attached to its prediction;
*   **constraint violations** -- options the engine called feasible that
    turned out not to be;
*   **operational reward** -- a stated scalar per domain, the same for every
    problem of that domain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from src.portwatch_os.decision.model import CARGO_CONNECTION, MINIMISE, OBJECTIVES, PORT_BERTHING, VESSEL_ROUTING
from src.portwatch_os.ledger.schema import DecisionProblemRecord

#: Objective the reward reads per domain, and its weight. Negative: a cost.
REWARD_TERMS: Dict[str, Dict[str, float]] = {
    VESSEL_ROUTING: {"eta": -1.0, "incident": -240.0},
    PORT_BERTHING: {"port_wait": -1.0, "missed_departures": -25.0},
    CARGO_CONNECTION: {"dwell": -0.5, "missed": -50.0},
}

CONFIDENCE_BINS = ((0.0, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01))


@dataclass
class ProblemScore:
    problem_id: str
    domain: str
    recommended: Optional[str]
    chosen: Optional[str]
    actual_action: Optional[str]
    agreed: Optional[bool]
    errors: Dict[str, Dict[str, float]] = field(default_factory=dict)
    regret: Optional[float] = None
    regret_objective: Optional[str] = None
    ranking_correct: Optional[bool] = None
    realised_best: Optional[str] = None
    constraint_violation: bool = False
    reward: Optional[float] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "problemId": self.problem_id, "domain": self.domain, "recommended": self.recommended,
            "chosen": self.chosen, "actualAction": self.actual_action, "agreed": self.agreed,
            "errors": self.errors, "regret": self.regret, "regretObjective": self.regret_objective,
            "rankingCorrect": self.ranking_correct, "realisedBest": self.realised_best,
            "constraintViolation": self.constraint_violation, "reward": self.reward, "notes": self.notes,
        }


def _option(problem: Dict[str, Any], option_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if option_id is None:
        return None
    return next((o for o in problem.get("options", []) if o.get("optionId") == option_id), None)


def _predicted(option: Optional[Dict[str, Any]], key: str) -> Optional[Dict[str, Any]]:
    if option is None or not option.get("evaluation"):
        return None
    measure = (option["evaluation"].get("objectives") or {}).get(key)
    if not measure or not measure.get("available"):
        return None
    return measure


def score_problem(record: DecisionProblemRecord) -> ProblemScore:
    """One resolved problem, scored from its record alone."""
    problem = record.problem or {}
    chosen_id = record.human_choice or record.recommended_option
    chosen = _option(problem, chosen_id)
    observed = dict(record.observed_outcome or {})
    score = ProblemScore(
        problem_id=record.problem_id, domain=record.domain, recommended=record.recommended_option,
        chosen=chosen_id, actual_action=record.actual_action,
        agreed=None if record.recommended_option is None or chosen_id is None
        else record.recommended_option == chosen_id,
    )

    # -- prediction error for the option taken ----------------------------
    for key, value in observed.items():
        if key not in OBJECTIVES or not isinstance(value, (int, float)):
            continue
        predicted = _predicted(chosen, key)
        if predicted is None:
            score.notes.append(f"{key}: observed but not predicted for {chosen_id}")
            continue
        error = float(value) - float(predicted["value"])
        score.errors[key] = {
            "predicted": round(float(predicted["value"]), 4), "observed": round(float(value), 4),
            "error": round(error, 4), "absoluteError": round(abs(error), 4),
            "confidence": predicted.get("confidence"),
        }

    # -- counterfactuals, where the outcome reveals every option ----------
    per_option = observed.get("optionOutcomes") if isinstance(observed.get("optionOutcomes"), dict) else None
    regret_key = _regret_objective(record.domain)
    if per_option and regret_key:
        realised = {oid: body.get(regret_key) for oid, body in per_option.items()
                    if isinstance(body, dict) and isinstance(body.get(regret_key), (int, float))}
        if realised:
            objective = OBJECTIVES[regret_key]
            best_id = (min if objective.direction == MINIMISE else max)(realised, key=lambda o: realised[o])
            score.realised_best = best_id
            score.regret_objective = regret_key
            if chosen_id in realised:
                score.regret = round(abs(realised[chosen_id] - realised[best_id]), 4)
            if record.recommended_option is not None:
                score.ranking_correct = record.recommended_option == best_id
    else:
        score.notes.append("only the option taken was observed; regret and ranking accuracy need "
                           "counterfactual outcomes")

    score.constraint_violation = bool(observed.get("constraintViolated"))
    score.reward = _reward(record.domain, observed)
    return score


def _regret_objective(domain: str) -> Optional[str]:
    return {VESSEL_ROUTING: "eta", PORT_BERTHING: "port_wait", CARGO_CONNECTION: "sailing"}.get(domain)


def _reward(domain: str, observed: Dict[str, Any]) -> Optional[float]:
    terms = REWARD_TERMS.get(domain)
    if not terms:
        return None
    total = 0.0
    used = False
    for key, weight in terms.items():
        value = observed.get(key)
        if isinstance(value, (int, float)):
            total += weight * float(value)
            used = True
    return round(total, 4) if used else None


def score_history(records: Sequence[DecisionProblemRecord]) -> Dict[str, Any]:
    """Aggregate scores over resolved problems."""
    resolved = [r for r in records if r.status == "resolved"]
    if not resolved:
        return {"available": False, "count": len(records), "resolved": 0,
                "note": "no decision has an observed outcome yet"}
    scores = [score_problem(r) for r in resolved]

    by_objective: Dict[str, List[float]] = {}
    signed: Dict[str, List[float]] = {}
    bins: Dict[str, List[float]] = {}
    for score in scores:
        for key, row in score.errors.items():
            by_objective.setdefault(key, []).append(row["absoluteError"])
            signed.setdefault(key, []).append(row["error"])
            confidence = row.get("confidence")
            if confidence is not None:
                for low, high in CONFIDENCE_BINS:
                    if low <= confidence < high:
                        bins.setdefault(f"{low:.1f}-{min(high, 1.0):.1f}", []).append(row["absoluteError"])
    agreed = [s.agreed for s in scores if s.agreed is not None]
    ranked = [s.ranking_correct for s in scores if s.ranking_correct is not None]
    regrets = [s.regret for s in scores if s.regret is not None]
    rewards = [s.reward for s in scores if s.reward is not None]
    return {
        "available": True,
        "count": len(records),
        "resolved": len(resolved),
        "agreementRate": round(sum(1 for a in agreed if a) / len(agreed), 4) if agreed else None,
        "rankingAccuracy": round(sum(1 for r in ranked if r) / len(ranked), 4) if ranked else None,
        "meanRegret": round(sum(regrets) / len(regrets), 4) if regrets else None,
        "meanReward": round(sum(rewards) / len(rewards), 4) if rewards else None,
        "constraintViolations": sum(1 for s in scores if s.constraint_violation),
        "predictionError": {
            key: {"meanAbsoluteError": round(sum(v) / len(v), 4), "bias": round(sum(signed[key]) / len(signed[key]), 4),
                  "count": len(v), "unit": OBJECTIVES[key].unit}
            for key, v in sorted(by_objective.items())
        },
        "calibration": {
            label: {"meanAbsoluteError": round(sum(v) / len(v), 4), "count": len(v)}
            for label, v in sorted(bins.items())
        },
        "problems": [s.to_dict() for s in scores],
        "method": (
            "scored from the ledger's stored problem payloads and observed outcomes only; the engine "
            "is never re-run with hindsight"
        ),
    }


__all__ = ["CONFIDENCE_BINS", "ProblemScore", "REWARD_TERMS", "score_history", "score_problem"]
