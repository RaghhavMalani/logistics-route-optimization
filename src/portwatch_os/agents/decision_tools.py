"""The decision engine as a tool, and the specialist that explains its output.

"What should MV Konkan do?" is answered by the deterministic engine, never by
a model. The tool below builds the world the attention queue is framed from,
finds the event that exposes the hull, runs the engine, and returns the
problem: the options, the rejected ones with their constraint, the frontier,
the ranking, the recommendation. The specialist reads that payload and
restates it -- "the safest option is X, the cheapest cannot be said because
no cost basis exists" -- and every sentence it produces points at an option
the engine computed. It does not invent a fourth option in prose.

Preferences in the question select among the engine's own picks:

    safest      -> LOWEST_RISK
    cheapest    -> LOWEST_COST (absent when nothing is priced, and said so)
    fastest     -> FASTEST
    do nothing  -> the baseline
    compare X with Y -> the two named options side by side
    within N h  -> options whose arrival is inside N hours, or none
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.agents.base import Agent, AgentRequest, AgentResult, Finding
from src.portwatch_os.agents.tools import SIMULATE, ToolCall, ToolRegistry, ToolUnavailable
from src.portwatch_os.decision.model import DecisionActor, DecisionProblem, SHIPPING_COMPANY

TOOL = "portwatch.decision.solve"

#: Words in the question that select one of the engine's labelled picks.
PREFERENCES: Tuple[Tuple[Tuple[str, ...], str], ...] = (
    (("safest", "lowest risk", "least risk", "avoid the storm", "avoid the risk"), "LOWEST_RISK"),
    (("cheapest", "lowest cost", "least cost"), "LOWEST_COST"),
    (("fastest", "quickest", "soonest", "earliest"), "FASTEST"),
    (("least fuel", "lowest fuel", "fuel"), "LOWEST_FUEL"),
    (("most reliable", "schedule reliability"), "BEST_SCHEDULE_RELIABILITY"),
)
_WITHIN = re.compile(r"within\s+(\d{1,3})\s*(?:h|hr|hrs|hour|hours)", re.IGNORECASE)
_ACTION_WORDS: Dict[str, Tuple[str, ...]] = {
    "REROUTE": ("reroute", "re-route", "rerouting", "divert", "diversion", "cape"),
    "SLOW_STEAM": ("slow steam", "slow-steam", "slow steaming", "hold", "wait"),
    "SPEED_UP": ("speed up", "faster"),
    "KEEP_PLAN": ("keep", "current route", "do nothing", "unchanged", "stay the course", "continue"),
    "CHANGE_DESTINATION_PORT": ("another port", "different port", "change destination"),
}


def preference_of(question: str) -> Optional[str]:
    lowered = (question or "").lower()
    for words, pick in PREFERENCES:
        if any(w in lowered for w in words):
            return pick
    return None


def compared_actions(question: str) -> List[str]:
    lowered = (question or "").lower()
    if "compar" not in lowered and " vs " not in lowered and " versus " not in lowered:
        return []
    found = [action for action, words in _ACTION_WORDS.items() if any(w in lowered for w in words)]
    return found


def within_hours(question: str) -> Optional[float]:
    match = _WITHIN.search(question or "")
    return float(match.group(1)) if match else None


def wants_baseline(question: str) -> bool:
    lowered = (question or "").lower()
    return any(w in lowered for w in ("do nothing", "current route", "keeps its", "keep its", "unchanged",
                                       "if it continues", "if we do nothing"))


# --------------------------------------------------------------------------
# the tool
# --------------------------------------------------------------------------


def register_decision_tools(registry: ToolRegistry, *, fleet, ledger) -> None:
    """Add the decision tool to a registry. Called by ``build_registry``."""
    from src.portwatch_os.decision.engine import get_engine
    from src.portwatch_os.global_eye.calibration import apply_calibration, fit_calibrator
    from src.portwatch_os.global_eye.ingest import from_news_bundle
    from src.portwatch_os.world.branch import ObservedWorldState
    from src.portwatch_os.world.build import build_world, seed_for
    from src.portwatch_os.world.cascade import propagate
    from src.portwatch_os.world.graph import EVENT, VESSEL, key
    from src.portwatch_os.world.live import Revision
    from src.portwatch_os.world.quantity import RISK, utc

    @registry.register(
        TOOL, SIMULATE,
        "Every feasible option for one exposed hull, simulated, criticised and ranked.",
        arguments={
            "vessel_id": "Fleet vessel id, e.g. PWD-001.",
            "vessel_name": "Fleet vessel name, e.g. MV Konkan, when no id is known.",
            "event_id": "Optional Global Eye event; defaults to the event exposing the hull soonest.",
            "at": "Optional ISO instant to query the world at; defaults to now.",
        },
        returns="The decision problem: options with objectives, rejected options with their "
                "constraint, the Pareto frontier, the ranking and the recommendation.",
        computed_by="src.portwatch_os.decision (deterministic; the world engine on scenario branches)",
        failure_modes=("The hull is not in the fleet.", "No live event exposes the hull at the instant.",
                       "The news bundle has not been exported."),
    )
    def decision_solve(
        vessel_id: Optional[str] = None,
        vessel_name: Optional[str] = None,
        event_id: Optional[str] = None,
        at: Optional[str] = None,
    ) -> Dict[str, Any]:
        from src.portwatch_os.agents.portwatch_tools import _read_cache

        vessel = None
        if vessel_id:
            vessel = fleet.vessel(vessel_id)
        elif vessel_name:
            wanted = vessel_name.strip().lower()
            vessel = next((v for v in fleet.vessels if v.name.lower() == wanted
                           or v.name.lower().replace("mv ", "") == wanted.replace("mv ", "")), None)
        if vessel is None:
            raise ToolUnavailable(f"{vessel_id or vessel_name or 'no vessel'} is not in the configured fleet")

        moment = utc(datetime.fromisoformat(at.replace("Z", "+00:00"))) if at else utc()
        bundle = _read_cache("news_bundle.json")
        events, _report = from_news_bundle(bundle)
        apply_calibration(events, fit_calibrator(ledger.event_outcomes(), fitted_at=utc().isoformat()))
        graph = build_world(events=events, voyages=fleet.voyages(), now=moment)
        state = ObservedWorldState(
            state_id=f"obs-tool-{int(moment.timestamp())}",
            revision=Revision("DEMO", fleet.company_id, f"{len(events)} events", f"{len(fleet.vessels)} hulls", 0),
            at=moment, graph=graph, traffic_mode="SIMULATED_TRAFFIC",
        )

        # The event to decide against: the one named, else the one whose
        # exposure reaches the hull with the tightest still-open window.
        candidates = [e for e in events if not event_id or e.event_id == event_id]
        exposing: List[Tuple[float, Any]] = []
        for event in candidates:
            seed_key = key(EVENT, event.event_id)
            if graph.node(seed_key) is None:
                continue
            cascade = propagate(graph, seed_key, seed_for(event), at=moment)
            reached = cascade.reached.get(key(VESSEL, vessel.vessel_id))
            if reached is None or RISK not in reached.quantities:
                continue
            hours = reached.quantities[RISK].attrs.get("hours_to_risk_area")
            exposing.append((hours if hours is not None else 1e9, event))
        if not exposing:
            raise ToolUnavailable(
                f"no live event exposes {vessel.name} at {moment.isoformat()}; there is no routing "
                "decision to make"
            )
        exposing.sort(key=lambda pair: pair[0])
        event = exposing[0][1]

        engine = get_engine()
        problem = engine.solve_vessel(
            state, event_key=key(EVENT, event.event_id), seed=seed_for(event), vessel_id=vessel.vessel_id,
            actor=DecisionActor(SHIPPING_COMPANY), at=moment,
        )
        return _summarise(problem, event)


def _summarise(problem: DecisionProblem, event) -> Dict[str, Any]:
    """The tool's payload: enough to explain, small enough to trace."""
    def measure(option, k):
        m = option.measure(k)
        return None if m is None or not m.available else round(m.value, 3)

    return {
        "decisionId": problem.decision_id,
        "vesselId": problem.subject_id,
        "vesselName": problem.subject_label,
        "eventId": event.event_id,
        "eventTitle": event.title,
        "at": problem.at,
        "headline": problem.headline,
        "doNothing": problem.do_nothing_statement,
        "decisionWindowHours": problem.decision_window_hours,
        "options": [
            {
                "optionId": o.option_id, "action": o.action, "label": o.label, "status": o.status,
                "isBaseline": o.is_baseline,
                "eta": measure(o, "eta"), "risk": measure(o, "risk"), "fuel": measure(o, "fuel"),
                "weather": measure(o, "weather"), "cost": measure(o, "cost"),
                "arrivalInHours": None if o.evaluation is None else o.evaluation.derived.get("arrivalInHours"),
                "weatherFlags": (o.measure("weather").attrs.get("flags") if o.measure("weather") and o.measure("weather").available else None),
                "rejectedBy": [c.detail for c in o.rejected_by],
                "critic": None if not o.critic else o.critic.get("verdict"),
                "unknown": [k for k, m in (o.evaluation.objectives.items() if o.evaluation else []) if not m.available],
            }
            for o in problem.options
        ],
        "notOffered": [
            {"kind": r["kind"], "status": r["availability"]["status"], "reason": r["availability"]["reason"]}
            for r in problem.available_actions if r["availability"]["status"] != "AVAILABLE"
        ],
        "frontier": None if problem.frontier is None else problem.frontier.to_dict(),
        "ranking": (problem.evidence.get("ranking") or {}).get("order"),
        "recommendation": None if problem.recommendation is None else {
            "optionId": problem.recommendation.option_id,
            "statement": problem.recommendation.statement,
            "critic": (problem.recommendation.critic or {}).get("verdict"),
        },
    }


# --------------------------------------------------------------------------
# the specialist
# --------------------------------------------------------------------------


class DecisionAgent(Agent):
    name = "decision"
    purpose = "Explain the engine's computed options for one hull; never invent one."
    allowed_tools = (TOOL,)
    max_access = SIMULATE
    failure_modes = (
        "The question names no vessel the fleet holds.",
        "No live event exposes the hull, so there is nothing to decide.",
        "A preference that no objective measures -- cheapest without a cost basis -- is reported as unmeasured.",
    )

    def run(self, request: AgentRequest) -> AgentResult:
        from src.portwatch_os.agents.specialists import _assemble

        calls: List[ToolCall] = []
        findings: List[Finding] = []
        vessel_name = _named_vessel(request.question)
        if not request.vessel_id and not vessel_name:
            return _assemble(self, calls, findings,
                             "No vessel was named, so there is no decision to compute. Name a hull.")
        call = self.call(TOOL, {"vessel_id": request.vessel_id, "vessel_name": vessel_name,
                                "event_id": request.event_id, "at": request.context.get("at")},
                         trace=calls)
        if not call.ok:
            return _assemble(self, calls, findings, f"No decision could be computed: {call.error}")

        body: Dict[str, Any] = call.result
        options = {o["optionId"]: o for o in body["options"]}
        feasible = [o for o in body["options"] if o["status"] == "FEASIBLE"]
        rejected = [o for o in body["options"] if o["status"] != "FEASIBLE"]
        picks = (body.get("frontier") or {}).get("picks") or {}
        recommendation = body.get("recommendation") or {}

        findings.append(Finding("Subject", body["vesselName"], call.tool, body["headline"]))
        findings.append(Finding("If unchanged", body["doNothing"], call.tool,
                                "The baseline, computed through the same simulator as every alternative."))
        findings.append(Finding("Feasible options", len(feasible), call.tool,
                                ", ".join(o["label"] for o in feasible) or "none", unit="options"))
        if rejected:
            findings.append(Finding("Rejected options", len(rejected), call.tool,
                                    "; ".join(f"{o['label']}: {'; '.join(o['rejectedBy'])}" for o in rejected),
                                    unit="options"))
        if body["notOffered"]:
            findings.append(Finding("Not offered", len(body["notOffered"]), call.tool,
                                    "; ".join(f"{r['kind']} ({r['status']})" for r in body["notOffered"]),
                                    unit="actions"))

        question = request.question
        preference = preference_of(question)
        focus: Optional[str] = None
        sentences: List[str] = []

        if wants_baseline(question):
            baseline = next((o for o in body["options"] if o["isBaseline"]), None)
            if baseline:
                focus = baseline["optionId"]
                sentences.append(f"{body['doNothing']}.")
        elif preference:
            chosen = picks.get(preference)
            if chosen and chosen in options:
                focus = chosen
                o = options[chosen]
                sentences.append(f"The {preference.replace('_', ' ').lower()} option is {o['label']}: "
                                 + _describe(o) + ".")
            else:
                objective = {"LOWEST_COST": "financial cost", "LOWEST_RISK": "risk", "FASTEST": "ETA",
                             "LOWEST_FUEL": "fuel", "BEST_SCHEDULE_RELIABILITY": "reliability"}.get(preference, preference)
                sentences.append(f"No option can be ranked on {objective}: it is not measured for every "
                                 "feasible option, so the engine does not name one.")
                if preference == "LOWEST_COST":
                    unknown = sorted({k for o in feasible for k in o["unknown"] if k == "cost"})
                    if unknown:
                        sentences.append("No cost basis is configured; enter a charter rate as a scenario "
                                         "assumption to price the options.")
        compare = compared_actions(question)
        if len(compare) >= 2:
            rows = [o for o in body["options"] if o["action"] in compare]
            if rows:
                sentences.append("Side by side: " + "; ".join(f"{o['label']} -- {_describe(o)}" for o in rows) + ".")
                focus = focus or rows[0]["optionId"]
            offered = {o["action"] for o in body["options"]}
            for action in compare:
                if action in offered:
                    continue
                absent = next((r for r in body["notOffered"] if r["kind"] == action), None)
                sentences.append(
                    f"{action.replace('_', ' ').title()} is not offered: "
                    + (absent["reason"] if absent else "it is not in the catalogue for this hull") + "."
                )
        limit = within_hours(question)
        if limit is not None:
            inside = [o for o in feasible if o["arrivalInHours"] is not None and o["arrivalInHours"] <= limit]
            if inside:
                sentences.append(f"Within {limit:.0f} h: " + ", ".join(
                    f"{o['label']} (arrives in {o['arrivalInHours']:.0f} h, risk {o['risk']})" for o in inside) + ".")
                if preference == "LOWEST_RISK":
                    best = min(inside, key=lambda o: (o["risk"] if o["risk"] is not None else 9, o["arrivalInHours"]))
                    focus = best["optionId"]
                    sentences.append(f"Of those, {best['label']} carries the least exposure.")
            else:
                sentences.append(f"No feasible option arrives within {limit:.0f} h.")
        if recommendation.get("optionId"):
            focus = focus or recommendation["optionId"]
            findings.append(Finding("Recommendation", options[recommendation["optionId"]]["label"], call.tool,
                                    recommendation.get("statement", ""),
                                    confidence=None))
            if not sentences:
                sentences.append(recommendation.get("statement", ""))
        summary = " ".join(s for s in sentences if s) or "The engine computed no feasible option."
        return _assemble(self, calls, findings, summary,
                         {"decisionId": body["decisionId"], "vesselId": body["vesselId"], "focusOptionId": focus,
                          "compare": len(feasible) > 1, "preference": preference,
                          "recommendationOptionId": recommendation.get("optionId"),
                          "options": body["options"], "frontier": body.get("frontier")})


def _describe(option: Dict[str, Any]) -> str:
    parts = []
    if option.get("eta") is not None:
        parts.append(f"ETA shift {option['eta']:+.0f} h")
    if option.get("risk") is not None:
        parts.append(f"risk {option['risk']:.2f}")
    if option.get("fuel") is not None:
        parts.append(f"fuel x{option['fuel']:.2f}")
    if option.get("weather") is not None:
        parts.append(f"worst wave {option['weather']:.1f} m")
    if option.get("cost") is not None:
        parts.append(f"cost {option['cost']:,.0f}")
    if option.get("unknown"):
        parts.append("unmeasured: " + ", ".join(option["unknown"][:3]))
    return ", ".join(parts) or "no measured objective"


_NAME = re.compile(r"\b(MV\s+[A-Z][a-z]+)\b")


def _named_vessel(question: str) -> Optional[str]:
    match = _NAME.search(question or "")
    return match.group(1) if match else None


__all__ = ["DecisionAgent", "TOOL", "compared_actions", "preference_of", "register_decision_tools",
           "wants_baseline", "within_hours"]
