"""The mission scorecard comparison: two incidents, one engine, one table.

A single replay proves the engine can be scored. Two structurally different
replays -- a strait blocked by a ship and two ports closed by a cyclone --
prove the scoring is not built around one incident. The comparison replays
each mission from its start instant, lets the engine decide every hull,
takes its own recommendation, reveals, and reads the same seven things off
each scorecard:

    forecast horizon        the claim horizon the register applied
    prediction error        how far the closure outlasted (or fell short of)
                            that horizon, in hours
    recommendation          what the engine said each hull should do
    best realised option    what the revealed outcome says it should have done
    regret                  the hours between the two, per hull and in total
    confidence calibration  the Brier score of the baseline exposure against
                            whether the place was in fact closed on arrival
    data completeness       how much of the recording carried a stated time,
                            how many sources, whether a queue figure exists

Deterministic: the same missions and the same engine produce the same
table, so the comparison can be a fixture and a claim.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from src.portwatch_os.decision.engine import DecisionEngine
from src.portwatch_os.decision.model import DecisionActor, SHIPPING_COMPANY
from src.portwatch_os.missions.catalogue import MISSIONS, get_mission
from src.portwatch_os.missions.replay import MissionReplay


def _mean(values: List[Optional[float]]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    return None if not clean else round(sum(clean) / len(clean), 3)


def scorecard_for(mission_id: str, *, engine: Optional[DecisionEngine] = None) -> Dict[str, Any]:
    """One mission replayed from its start, decided by the engine, revealed."""
    mission = get_mission(mission_id)
    engine = engine or DecisionEngine(capacity=64)
    replay = MissionReplay(mission, engine, replay_id=f"compare-{mission_id}")
    actor = DecisionActor(SHIPPING_COMPANY, vessel_ids=tuple(v.vessel_id for v in mission.fleet))
    refused: Dict[str, str] = {}
    for hull in mission.fleet:
        try:
            replay.decide(hull.vessel_id, actor)
        except Exception as exc:  # noqa: BLE001 - a refusal is part of the record
            refused[hull.vessel_id] = f"{type(exc).__name__}: {exc}"
    revealed = replay.reveal()
    cards = revealed["scorecards"]

    hulls = []
    for hull in mission.fleet:
        card = cards.get(hull.vessel_id)
        if card is None:
            hulls.append({"vesselId": hull.vessel_id, "name": hull.name, "refused": refused.get(hull.vessel_id)})
            continue
        realised = card["realised"]
        recommended = card["recommended"]["optionId"]
        hulls.append({
            "vesselId": hull.vessel_id,
            "name": hull.name,
            "destinationPort": hull.destination_port,
            "recommended": recommended,
            "recommendedRealisedHours": None if recommended not in realised else realised[recommended]["hours"],
            "critic": card["recommended"]["critic"],
            "realisedBest": card["realisedBest"],
            "realisedBestHours": None if card["realisedBest"] is None else realised[card["realisedBest"]]["hours"],
            "regretHours": card["regretHours"],
            "rankingCorrect": card["rankingCorrect"],
            "closedOnArrival": card["forecastError"]["closedOnArrival"],
            "baselineRisk": card["predicted"]["baselineRisk"],
            "brier": card["forecastError"]["brier"],
            "persistenceErrorHours": card["forecastError"]["persistenceErrorHours"],
            "blockedHours": card["forecastError"]["blockedHours"],
            "subject": card["forecastError"].get("subject") or mission.chokepoint,
            "learned": card["learned"],
        })

    timed = sum(1 for o in mission.recording if not o.time_unstated)
    visible_at_start = len(mission.visible(mission.start))
    regrets = [h.get("regretHours") for h in hulls if h.get("regretHours") is not None]
    return {
        "missionId": mission.mission_id,
        "name": mission.name,
        "subjectKind": mission.subject_kind,
        "subject": mission.subject,
        "eventCategory": mission.event_category,
        "startTimestamp": mission.start_timestamp,
        "forecastHorizonHours": mission.claim_horizon_hours,
        "outcome": {
            "blockedHours": round(mission.outcome.blocked_hours, 1),
            "closures": mission.outcome.to_dict()["closures"],
            "shipsWaitingPeak": mission.outcome.ships_waiting_peak,
        },
        "predictionErrorHours": _mean([h.get("persistenceErrorHours") for h in hulls]),
        "hulls": hulls,
        "regret": {
            "totalHours": None if not regrets else round(sum(regrets), 1),
            "meanHours": _mean(regrets),
            "hullsWithZeroRegret": sum(1 for r in regrets if r == 0),
            "hullsScored": len(regrets),
        },
        "rankingCorrectShare": _mean([1.0 if h.get("rankingCorrect") else 0.0 for h in hulls
                                      if h.get("rankingCorrect") is not None]),
        "calibration": {
            "meanBrier": _mean([h.get("brier") for h in hulls]),
            "meanBaselineRisk": _mean([h.get("baselineRisk") for h in hulls]),
            "closedOnArrivalShare": _mean([1.0 if h.get("closedOnArrival") else 0.0 for h in hulls
                                           if h.get("closedOnArrival") is not None]),
        },
        "dataCompleteness": {
            "observations": len(mission.recording),
            "withStatedTime": timed,
            "statedTimeShare": round(timed / max(1, len(mission.recording)), 3),
            "sources": len(mission.sources),
            "visibleAtStart": visible_at_start,
            "hiddenAtStart": len(mission.recording) - visible_at_start,
            "queueFigureStated": mission.outcome.ships_waiting_peak is not None,
        },
        "refused": refused,
        "disclaimer": mission.disclaimer,
    }


def compare_missions(mission_ids: Optional[Sequence[str]] = None, *, engine: Optional[DecisionEngine] = None) -> Dict[str, Any]:
    ids = list(mission_ids or MISSIONS)
    cards = [scorecard_for(mid, engine=engine) for mid in ids]
    rows = [
        ("forecastHorizonHours", "Forecast horizon (h)"),
        ("predictionErrorHours", "Prediction error: closure minus horizon (h)"),
        ("regret.meanHours", "Mean regret per hull (h)"),
        ("regret.totalHours", "Total regret (h)"),
        ("rankingCorrectShare", "Recommendation was the realised best (share of hulls)"),
        ("calibration.meanBrier", "Calibration: mean Brier of baseline exposure"),
        ("calibration.closedOnArrivalShare", "Hulls that met the closure on arrival (share)"),
        ("dataCompleteness.statedTimeShare", "Observations with a stated time (share)"),
        ("dataCompleteness.sources", "Sources cited"),
        ("dataCompleteness.queueFigureStated", "Queue figure stated by a source"),
    ]

    def read(card: Dict[str, Any], path: str) -> Any:
        node: Any = card
        for part in path.split("."):
            node = None if node is None else node.get(part)
        return node

    table = [{"key": key, "label": label, "values": {c["missionId"]: read(c, key) for c in cards}} for key, label in rows]
    return {"missions": cards, "table": table, "note": (
        "Each mission is replayed from its start instant with only the observations knowable then; the engine "
        "decides every illustrative hull, its own recommendation is taken, and the outcome is revealed. The "
        "figures are the scorecards' own, read the same way for both."
    )}


__all__ = ["compare_missions", "scorecard_for"]
