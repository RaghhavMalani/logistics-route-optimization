"""Critic v2: every candidate option judged before it is ranked, and every
verdict tied to the computation or evidence that produced it.

The first Critic judged agent chains. This one judges decision options, and
the discipline is the same: it checks whether an option is supported, safe
and consistent with the evidence behind it; it never re-derives the option,
never relaxes a hard constraint, and cannot turn a rejected option into an
approved one. What is new is the scope -- a decision option carries its own
constraint results, its own measures with their confidences and bases, its
branch's assumptions and the state of the data it rested on -- and the
Critic reads all of it.

Three verdicts:

    PASS                every check held
    PASS_WITH_WARNINGS  actionable, shown with the warnings attached
    REJECT              not put in front of an operator as a choice

Each check names its ``basis``: the constraint key, the measure key, the
branch id, the evidence field. "The Critic rejected it" is never the whole
answer; "the Critic rejected it because ``route_topology`` failed on branch
br-0007" is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from src.portwatch_os.decision.model import (
    DecisionOption,
    DecisionProblem,
    REJECTED,
)

PASS = "PASS"
PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
REJECT = "REJECT"
VERDICTS = (PASS, PASS_WITH_WARNINGS, REJECT)

BLOCKING = "blocking"
WARNING = "warning"

#: Evidence older than this is flagged. Same budget as the agent Critic.
STALE_HOURS = 18.0
#: Below this the weather figure is a hint, not evidence.
MIN_WEATHER_CONFIDENCE = 0.25
#: A window shorter than this is flagged as urgent.
URGENT_WINDOW_HOURS = 2.0
#: Two figures for one quantity further apart than this are a disagreement.
DISAGREEMENT_FRACTION = 0.35


@dataclass
class Check:
    name: str
    passed: bool
    severity: str
    detail: str
    basis: str
    remedy: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "severity": self.severity,
                "detail": self.detail, "basis": self.basis, "remedy": self.remedy}


@dataclass
class Verdict:
    verdict: str
    checks: List[Check] = field(default_factory=list)
    ran_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    @property
    def failed(self) -> List[Check]:
        return [c for c in self.checks if not c.passed]

    @property
    def reasons(self) -> List[str]:
        return [f"{c.name}: {c.detail}" for c in self.failed]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "checks": [c.to_dict() for c in self.checks],
            "failed": [c.name for c in self.failed],
            "reasons": self.reasons,
            "warnings": [c.to_dict() for c in self.failed if c.severity == WARNING],
            "blocking": [c.to_dict() for c in self.failed if c.severity == BLOCKING],
            "ranAt": self.ran_at,
        }


def _verdict(checks: Sequence[Check]) -> Verdict:
    blocking = [c for c in checks if not c.passed and c.severity == BLOCKING]
    warnings = [c for c in checks if not c.passed and c.severity == WARNING]
    return Verdict(REJECT if blocking else PASS_WITH_WARNINGS if warnings else PASS, list(checks))


class DecisionCritic:
    """Judges options. Cannot create, relax or promote one."""

    name = "decision_critic"

    def review_option(
        self,
        option: DecisionOption,
        problem: DecisionProblem,
        *,
        now: Optional[datetime] = None,
    ) -> Verdict:
        moment = now or datetime.now(timezone.utc)
        checks: List[Check] = []
        checks.append(self._hard_constraints(option))
        checks.append(self._decision_window(option, problem))
        checks.append(self._source_freshness(problem, moment))
        checks.append(self._weather_confidence(option))
        checks.append(self._model_disagreement(option, problem))
        checks.append(self._route_feasibility(option))
        checks.append(self._port_feasibility(option))
        checks.append(self._cargo_feasibility(option))
        checks.append(self._data_availability(option, problem))
        checks.append(self._assumptions(option))
        checks.append(self._claim_horizon(option))
        return _verdict(checks)

    def review_recommendation(
        self,
        problem: DecisionProblem,
        option_id: Optional[str],
    ) -> Verdict:
        """The recommendation as a whole: it must rest on a passing option and
        say what it traded away."""
        checks: List[Check] = []
        option = None if option_id is None else problem.option(option_id)
        if option is None:
            checks.append(Check("recommendation_exists", False, BLOCKING,
                                "no feasible option survived evaluation", basis="problem.options"))
            return _verdict(checks)
        own = option.critic or {}
        checks.append(Check(
            "recommended_option_passes", own.get("verdict") != REJECT, BLOCKING,
            f"{option.option_id} carries verdict {own.get('verdict')}",
            basis=f"critic of option {option.option_id}",
        ))
        picks = problem.frontier.picks if problem.frontier else {}
        lowest_risk = picks.get("LOWEST_RISK")
        risk_here = option.measure("risk")
        risk_best = problem.option(lowest_risk).measure("risk") if lowest_risk and problem.option(lowest_risk) else None
        worse_than_best = (
            lowest_risk is not None and lowest_risk != option.option_id
            and risk_here is not None and risk_best is not None
            and risk_here.available and risk_best.available
            and risk_here.value > risk_best.value + 1e-9
        )
        if worse_than_best:
            checks.append(Check(
                "risk_tradeoff_stated", False, WARNING,
                f"{option.option_id} is not the lowest-risk option ({lowest_risk}"
                + (f", risk {risk_best.value:.2f}" if risk_best and risk_best.available else "")
                + (f" against {risk_here.value:.2f}" if risk_here and risk_here.available else "") + ")",
                basis="frontier.picks.LOWEST_RISK",
                remedy="show the lower-risk alternative beside the recommendation",
            ))
        else:
            checks.append(Check("risk_tradeoff_stated", True, WARNING,
                                "no feasible option carries lower risk than the recommendation"
                                if risk_here is not None else "no risk objective in this domain",
                                basis="frontier.picks.LOWEST_RISK"))
        if problem.frontier and option.option_id in problem.frontier.dominated:
            checks.append(Check(
                "not_dominated", False, BLOCKING,
                f"{option.option_id} is dominated by {problem.frontier.dominated[option.option_id]}",
                basis="frontier.dominated",
            ))
        else:
            checks.append(Check("not_dominated", True, BLOCKING,
                                "the recommendation is on the frontier", basis="frontier.nondominated"))
        return _verdict(checks)

    # -- checks ------------------------------------------------------------
    def _hard_constraints(self, option: DecisionOption) -> Check:
        failed = option.rejected_by
        if failed:
            return Check("hard_constraints", False, BLOCKING,
                         "; ".join(f"{c.key}: {c.detail}" for c in failed),
                         basis="; ".join(c.basis for c in failed))
        return Check("hard_constraints", True, BLOCKING,
                     f"{sum(1 for c in option.constraints if c.hard)} hard constraint(s) held",
                     basis=", ".join(c.key for c in option.constraints if c.hard) or "none")

    def _decision_window(self, option: DecisionOption, problem: DecisionProblem) -> Check:
        closes = option.provenance.get("closesInHours")
        if closes is None:
            return Check("decision_window", True, WARNING, "the option does not close",
                         basis="option.provenance.closesInHours")
        if closes <= 0:
            return Check("decision_window", False, BLOCKING,
                         f"the option closed {abs(closes):.1f} h ago", basis="option.provenance.closesInHours")
        if closes < URGENT_WINDOW_HOURS:
            return Check("decision_window", False, WARNING, f"only {closes:.1f} h remain before the option closes",
                         basis="option.provenance.closesInHours", remedy="mark urgent; show the deadline")
        return Check("decision_window", True, WARNING, f"{closes:.1f} h remain",
                     basis="option.provenance.closesInHours")

    def _source_freshness(self, problem: DecisionProblem, now: datetime) -> Check:
        at = problem.at
        try:
            queried = datetime.fromisoformat(at.replace("Z", "+00:00")) if at else None
        except ValueError:
            queried = None
        if queried is None:
            return Check("source_freshness", True, WARNING, "no query instant recorded", basis="problem.at")
        age = abs((now - queried).total_seconds()) / 3600.0
        replay = problem.evidence.get("replay")
        if replay:
            return Check("source_freshness", True, WARNING,
                         f"replay clock {at}: the world is as it was then by construction",
                         basis="problem.evidence.replay")
        if age > STALE_HOURS:
            return Check("source_freshness", False, WARNING,
                         f"the world was queried {age:.0f} h from now, beyond the {STALE_HOURS:.0f} h budget",
                         basis="problem.at", remedy="attach the query instant to the recommendation")
        return Check("source_freshness", True, WARNING, f"queried {age:.1f} h from now", basis="problem.at")

    def _weather_confidence(self, option: DecisionOption) -> Check:
        weather = option.measure("weather")
        if weather is None:
            return Check("weather_confidence", True, WARNING, "no weather objective in this domain",
                         basis="objectives.weather")
        if not weather.available:
            return Check("weather_confidence", False, WARNING, weather.unknown_because or "weather unknown",
                         basis="objectives.weather", remedy="state that the passage was not weather-checked")
        if (weather.confidence or 0.0) < MIN_WEATHER_CONFIDENCE:
            return Check("weather_confidence", False, WARNING,
                         f"weather confidence {weather.confidence:.2f} below {MIN_WEATHER_CONFIDENCE:.2f} "
                         f"(coverage {weather.attrs.get('coverage')})",
                         basis="objectives.weather (route_exposure.sample_route)")
        return Check("weather_confidence", True, WARNING,
                     f"worst wave {weather.value:.1f} m at confidence {weather.confidence:.2f}",
                     basis="objectives.weather (route_exposure.sample_route)")

    def _model_disagreement(self, option: DecisionOption, problem: DecisionProblem) -> Check:
        routes = problem.evidence.get("routes") or {}
        geometry_detour = routes.get("detourNm")
        lane_code = routes.get("laneCode")
        if option.action not in ("REROUTE", "SPEED_UP") or geometry_detour is None:
            return Check("model_disagreement", True, WARNING, "no second figure to compare against",
                         basis="evidence.routes")
        from src.portwatch_os.global_eye.exposure import TRADE_LANES

        lane = TRADE_LANES.get(lane_code or "")
        catalogue = None if lane is None else lane.detour_nm
        if not catalogue:
            return Check("model_disagreement", True, WARNING, "the lane catalogue holds no detour figure",
                         basis="TRADE_LANES.detour_nm")
        gap = abs(geometry_detour - catalogue) / catalogue
        if gap > DISAGREEMENT_FRACTION:
            return Check(
                "model_disagreement", False, WARNING,
                f"route geometry puts the detour at {geometry_detour:.0f} nm from here; the lane catalogue's "
                f"origin-to-destination detour is {catalogue:.0f} nm ({gap:.0%} apart) -- the hull's position "
                "along the lane accounts for the difference and both are shown",
                basis="evidence.routes.detourNm vs TRADE_LANES.detour_nm",
                remedy="show both figures",
            )
        return Check("model_disagreement", True, WARNING,
                     f"geometry detour {geometry_detour:.0f} nm within {DISAGREEMENT_FRACTION:.0%} of the "
                     f"catalogue's {catalogue:.0f} nm", basis="evidence.routes.detourNm vs TRADE_LANES.detour_nm")

    def _route_feasibility(self, option: DecisionOption) -> Check:
        topology = next((c for c in option.constraints if c.key == "route_topology"), None)
        if topology is None:
            return Check("route_feasibility", True, BLOCKING, "the option does not change routing",
                         basis="constraints.route_topology")
        return Check("route_feasibility", topology.passed, BLOCKING, topology.detail, basis=topology.basis)

    def _port_feasibility(self, option: DecisionOption) -> Check:
        pressure = option.measure("yard_pressure") or option.measure("port_wait")
        if pressure is None:
            return Check("port_feasibility", True, WARNING, "no port objective in this domain",
                         basis="objectives")
        if not pressure.available:
            return Check("port_feasibility", False, WARNING, pressure.unknown_because or "port consequence unknown",
                         basis="objectives.yard_pressure", remedy="state that the port consequence is unmodelled")
        return Check("port_feasibility", True, WARNING, f"port consequence measured: {pressure.value:.3f} {pressure.unit}",
                     basis=pressure.basis)

    def _cargo_feasibility(self, option: DecisionOption) -> Check:
        cargo = option.measure("missed_connection") or option.measure("slack")
        if cargo is None:
            return Check("cargo_feasibility", True, WARNING, "no cargo objective in this domain", basis="objectives")
        if not cargo.available:
            return Check("cargo_feasibility", False, WARNING, cargo.unknown_because or "cargo consequence unknown",
                         basis="objectives.missed_connection", remedy="state that cargo is not linked")
        return Check("cargo_feasibility", True, WARNING, f"cargo consequence measured: {cargo.value:.1f} {cargo.unit}",
                     basis=cargo.basis)

    def _data_availability(self, option: DecisionOption, problem: DecisionProblem) -> Check:
        gaps: List[str] = []
        marine = (problem.evidence.get("marine") or {}).get("available")
        if marine is False:
            gaps.append("no marine grid (licence mode or fetch)")
        financial = option.evaluation.financial if option.evaluation else None
        if financial and financial.get("unknown"):
            gaps.append("unpriced: " + ", ".join(u["label"] for u in financial["unknown"]))
        if gaps:
            return Check("data_availability", False, WARNING, "; ".join(gaps),
                         basis="evidence.marine; evaluation.financial.unknown",
                         remedy="show the unknown components as unknown, never as zero")
        return Check("data_availability", True, WARNING, "every input the option needs is available",
                     basis="evidence.marine; evaluation.financial")

    def _assumptions(self, option: DecisionOption) -> Check:
        branch = [a.get("kind") for a in option.assumptions]
        financial = option.evaluation.financial if option.evaluation else None
        assumed_rates = [c["label"] for c in (financial or {}).get("components", []) if c.get("isAssumption")]
        if assumed_rates:
            return Check("assumptions", False, WARNING,
                         f"priced with operator assumptions: {', '.join(assumed_rates)}"
                         + (f"; branch assumptions: {', '.join(branch)}" if branch else ""),
                         basis="evaluation.financial.components[].isAssumption; option.assumptions",
                         remedy="label every figure built on them ASSUMPTION")
        return Check("assumptions", True, WARNING,
                     f"branch assumptions: {', '.join(branch) if branch else 'none'}; no assumed rates",
                     basis="option.assumptions")

    def _claim_horizon(self, option: DecisionOption) -> Check:
        risk = option.measure("risk")
        if risk is None or not risk.available:
            return Check("claim_horizon", True, WARNING, "no residual-risk figure", basis="objectives.risk")
        if risk.attrs.get("arrivalAfterClaimHorizon"):
            return Check("claim_horizon", False, WARNING,
                         "the option's exposure is zero because the hull arrives after the claim lapses; "
                         "persistence of the disruption beyond the claim horizon is not modelled",
                         basis=risk.basis, remedy="show the claim horizon beside the risk figure")
        return Check("claim_horizon", True, WARNING, "the residual risk is read within the claim horizon",
                     basis=risk.basis)

    @classmethod
    def describe(cls) -> Dict[str, Any]:
        return {
            "name": cls.name,
            "verdicts": list(VERDICTS),
            "checks": ["hard_constraints", "decision_window", "source_freshness", "weather_confidence",
                       "model_disagreement", "route_feasibility", "port_feasibility", "cargo_feasibility",
                       "data_availability", "assumptions", "claim_horizon"],
            "recommendationChecks": ["recommended_option_passes", "risk_tradeoff_stated", "not_dominated"],
            "note": "Every check names the computation or evidence it read. The Critic never relaxes a "
                    "hard constraint and never promotes a rejected option.",
        }


__all__ = [
    "BLOCKING",
    "Check",
    "DISAGREEMENT_FRACTION",
    "DecisionCritic",
    "MIN_WEATHER_CONFIDENCE",
    "PASS",
    "PASS_WITH_WARNINGS",
    "REJECT",
    "STALE_HOURS",
    "URGENT_WINDOW_HOURS",
    "VERDICTS",
    "Verdict",
    "WARNING",
]
