"""The specialist agents.

Each one owns a question, a set of tools and a way of reconciling what those
tools return. None of them contains business logic: where a specialist appears
to compute something, it is selecting or filtering values a tool produced, and
every :class:`Finding` names the tool it came from.

The reconciliation is where an agent earns its keep. A tool returns a list of
exposures; the operator needs "seven vessels, of which four can still divert and
three cannot, with the earliest deadline in eleven hours". Turning the first into
the second -- while keeping the timing gate that says which is which -- is the
agent's job.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from src.portwatch_os.agents.base import (
    BLOCKED,
    COMPLETE,
    PARTIAL,
    Agent,
    AgentRequest,
    AgentResult,
    Finding,
    propagate_confidence,
    summarise_gaps,
)
from src.portwatch_os.agents.tools import PROPOSE, READ, SIMULATE, ToolCall

#: Confidence attributed to a tool result by what produced it. A deterministic
#: model over exported artefacts is trusted more than a heuristic over a news
#: feed, and the numbers say so rather than every source reading as equal.
_SOURCE_CONFIDENCE: Dict[str, float] = {
    "portwatch.ports.get": 0.92,
    "portwatch.ports.list": 0.92,
    "portwatch.forecast.get": 0.85,
    "portwatch.weather.get": 0.80,
    "portwatch.global_eye.events": 0.62,
    "portwatch.global_eye.exposure": 0.62,
    "portwatch.company.fleet": 0.70,
    "portwatch.company.risk": 0.62,
    "portwatch.port_twin.state": 0.78,
    "portwatch.port_twin.simulate": 0.80,
    "portwatch.port_twin.benchmark": 0.88,
    "portwatch.cargo.opportunities": 0.55,
    "portwatch.cargo.optimize": 0.55,
    "portwatch.routing.optimize": 0.65,
    "portwatch.scenarios.simulate": 0.70,
    "portwatch.learning.outcomes": 0.90,
    "portwatch.learning.reliability": 0.90,
    "portwatch.learning.policies": 0.95,
    "portwatch.advisories.list": 0.95,
    "portwatch.provenance.get": 0.98,
}


def _confidence_of(call: ToolCall) -> Optional[float]:
    if not call.ok:
        return None
    return _SOURCE_CONFIDENCE.get(call.tool, 0.6)


def _assemble(
    agent: Agent,
    calls: Sequence[ToolCall],
    findings: List[Finding],
    summary: str,
    data: Optional[Dict[str, Any]] = None,
) -> AgentResult:
    gaps = summarise_gaps(calls)
    failures = sum(1 for c in calls if not c.ok)
    confidence = propagate_confidence(
        [_confidence_of(c) for c in calls], failures=failures, gaps=len(gaps)
    )
    outcome = (
        BLOCKED if not any(c.ok for c in calls)
        else PARTIAL if failures else COMPLETE
    )
    return AgentResult(
        agent=agent.name, outcome=outcome, summary=summary, findings=findings,
        calls=list(calls), confidence=confidence, gaps=gaps, data=data or {},
    )


# --------------------------------------------------------------------------
# Global Eye
# --------------------------------------------------------------------------


class GlobalEyeAgent(Agent):
    name = "global_eye"
    purpose = (
        "Find the disruptions that matter now and trace each one through "
        "chokepoints and trade lanes to the ports and vessels it touches."
    )
    allowed_tools = ("portwatch.global_eye.events", "portwatch.global_eye.exposure")
    max_access = READ
    failure_modes = (
        "The news bundle has not been exported, in which case no event is reported "
        "rather than an empty world being implied.",
        "An event carries no chokepoint, so no lane exposure can be computed and the "
        "event is reported for awareness only.",
        "No calibrated probability exists for the category, so severity and "
        "confidence are reported instead of a percentage.",
    )

    def run(self, request: AgentRequest) -> AgentResult:
        calls: List[ToolCall] = []
        findings: List[Finding] = []

        listed = self.call(
            "portwatch.global_eye.events", {"limit": 25}, trace=calls
        )
        if not listed.ok:
            return _assemble(
                self, calls, findings,
                "No event feed is available, so Global Eye cannot report anything. "
                "That is an absence of data, not an absence of disruption.",
            )

        events: List[Dict[str, Any]] = listed.result.get("events", [])
        calibration = listed.result.get("calibration", {})

        findings.append(Finding(
            "Events in scope", len(events), listed.tool,
            f"Merged from {listed.result.get('ingest', {}).get('rawItems', 0)} feed items.",
            unit="events",
        ))

        severe = [e for e in events if e["severity"] >= 0.6 and e["confidence"] >= 0.5]
        findings.append(Finding(
            "Severe and corroborated", len(severe), listed.tool,
            "Severity at or above 0.60 with at least two independent outlets.",
            unit="events",
        ))
        if not calibration.get("available"):
            findings.append(Finding(
                "Calibrated probabilities", "unavailable", listed.tool,
                f"Only {calibration.get('globalCount', 0)} event claims have resolved. "
                "Severity and confidence are reported instead of a probability.",
            ))

        # The lead event is the one the chain is traced through: the strongest
        # combination of how bad, how sure and how recent.
        target_id = request.event_id or (
            max(events, key=lambda e: e["severity"] * e["confidence"])["eventId"]
            if events else None
        )
        impact: Dict[str, Any] = {}
        if target_id:
            traced = self.call(
                "portwatch.global_eye.exposure",
                {"event_id": target_id, "company_id": request.company_id},
                trace=calls,
            )
            if traced.ok:
                impact = traced.result
                lanes = impact.get("lanes", [])
                ports = impact.get("ports", [])
                vessels = impact.get("vessels", [])
                findings.append(Finding(
                    "Lead event", impact.get("title", target_id), traced.tool,
                    f"{impact.get('categoryLabel', '')} · "
                    f"{impact.get('sourceCount', 0)} sources · "
                    f"severity {impact.get('severity')} · "
                    f"confidence {impact.get('confidence')}",
                ))
                if lanes:
                    findings.append(Finding(
                        "Trade lanes exposed", len(lanes), traced.tool,
                        "Worst: " + ", ".join(
                            f"{l['laneName']} ({l['exposure']:.2f})" for l in lanes[:3]
                        ), unit="lanes",
                    ))
                if vessels:
                    committed = sum(1 for v in vessels if v["alreadyEntered"])
                    findings.append(Finding(
                        "Vessels exposed", len(vessels), traced.tool,
                        f"{len(vessels) - committed} can still divert; {committed} have "
                        "already entered the risk area and cannot.",
                        unit="vessels",
                    ))
                if ports:
                    findings.append(Finding(
                        "Ports exposed", len(ports), traced.tool,
                        "Highest: " + ", ".join(
                            f"{p['portCode']} ({p['exposure']:.2f})" for p in ports[:4]
                        ), unit="ports",
                    ))

        summary = (
            f"{len(events)} events in scope, {len(severe)} severe and corroborated."
            + (
                f" The lead item is {impact.get('title', '')[:80]}, exposing "
                f"{len(impact.get('lanes', []))} trade lanes and "
                f"{len(impact.get('ports', []))} Indian ports."
                if impact else " No event could be traced to a chokepoint."
            )
        )
        return _assemble(self, calls, findings, summary,
                         {"events": events, "impact": impact})


# --------------------------------------------------------------------------
# Weather
# --------------------------------------------------------------------------


class WeatherAgent(Agent):
    name = "weather"
    purpose = "Report marine conditions and the forward operational impact at a port."
    allowed_tools = ("portwatch.weather.get",)
    max_access = READ
    failure_modes = (
        "The weather artefact has not been exported.",
        "Significant wave height is not carried by the marine feed and is reported "
        "as unavailable rather than substituted.",
    )

    def run(self, request: AgentRequest) -> AgentResult:
        calls: List[ToolCall] = []
        findings: List[Finding] = []
        call = self.call(
            "portwatch.weather.get",
            {"port_code": request.port_code} if request.port_code else {},
            trace=calls,
        )
        if not call.ok:
            return _assemble(
                self, calls, findings,
                "No weather artefact is available for this run.",
            )

        signal = call.result if isinstance(call.result, dict) else None
        if signal is None:
            rows = call.result if isinstance(call.result, list) else []
            worst = max(rows, key=lambda r: r.get("impactScore") or 0.0) if rows else None
            if worst:
                findings.append(Finding(
                    "Worst forward impact", worst.get("impactScore"), call.tool,
                    f"{worst.get('name')} — {worst.get('advisory', '')}",
                    unit="index",
                ))
            findings.append(Finding("Stations reporting", len(rows), call.tool,
                                    "Port weather stations in this run.", unit="stations"))
            summary = (
                f"{len(rows)} port weather stations reporting."
                + (f" Highest forward impact at {worst.get('name')}." if worst else "")
            )
            return _assemble(self, calls, findings, summary, {"stations": rows})

        for label, key, unit in (
            ("Wind", "windKnots", "kn"), ("Gust", "gustKnots", "kn"),
            ("Rainfall 24h", "rainfallMm24h", "mm"),
            ("Visibility", "visibilityKm", "km"),
            ("Storm risk", "stormRisk", "index"),
            ("Operational impact", "impactScore", "index"),
        ):
            if signal.get(key) is not None:
                findings.append(Finding(label, signal[key], call.tool,
                                        signal.get("advisory", ""), unit=unit))
        findings.append(Finding(
            "Significant wave height", None, call.tool,
            "The marine feed carries no wave height for these stations. Reported as "
            "unavailable rather than substituted with a modelled sea state.",
        ))

        summary = (
            f"{signal.get('name', request.port_code)}: "
            f"{signal.get('advisory', 'no advisory')} "
            f"(impact index {signal.get('impactScore')})."
        )
        return _assemble(self, calls, findings, summary, {"signal": signal})


# --------------------------------------------------------------------------
# Fleet
# --------------------------------------------------------------------------


class FleetAgent(Agent):
    name = "fleet"
    purpose = "Identify which vessels in a company fleet require intervention, and when."
    allowed_tools = ("portwatch.company.fleet", "portwatch.company.risk")
    max_access = READ
    failure_modes = (
        "No company account is configured.",
        "Fleet positions are simulated in this deployment and are labelled as such; "
        "no licensed AIS feed is connected.",
    )

    def run(self, request: AgentRequest) -> AgentResult:
        calls: List[ToolCall] = []
        findings: List[Finding] = []

        profile = self.call(
            "portwatch.company.fleet", {"company_id": request.company_id}, trace=calls
        )
        risk = self.call(
            "portwatch.company.risk", {"horizon_hours": request.horizon_hours}, trace=calls
        )
        if not risk.ok:
            return _assemble(
                self, calls, findings,
                "Fleet exposure could not be computed for this run.",
            )

        rows: List[Dict[str, Any]] = risk.result.get("rows", [])
        exposed = {r["vesselId"] for r in rows}
        actionable = [r for r in rows if not r["alreadyEntered"]]
        committed = [r for r in rows if r["alreadyEntered"]]
        deadlines = [r["diversionDeadline"] for r in actionable if r.get("diversionDeadline")]

        if profile.ok:
            findings.append(Finding(
                "Fleet size", profile.result.get("vesselCount"), profile.tool,
                f"{profile.result.get('name')} — positions are "
                f"{profile.result.get('positionSource')}.", unit="vessels",
            ))
        findings.append(Finding(
            "Vessels exposed", len(exposed), risk.tool,
            f"Within the next {request.horizon_hours:.0f} hours.", unit="vessels",
        ))
        findings.append(Finding(
            "Still divertible", len({r["vesselId"] for r in actionable}), risk.tool,
            "Short of the risk area, so a routing change is still available.",
            unit="vessels",
        ))
        findings.append(Finding(
            "Already committed", len({r["vesselId"] for r in committed}), risk.tool,
            "Inside the exposed water. No routing action is available; these are for "
            "monitoring, not for diversion.", unit="vessels",
        ))
        if deadlines:
            findings.append(Finding(
                "Earliest diversion deadline", min(deadlines), risk.tool,
                "The first point at which an option closes.",
            ))

        port_risk = risk.result.get("portRisk", {})
        if port_risk:
            worst = sorted(port_risk.values(), key=lambda p: -p["risk"])[:3]
            findings.append(Finding(
                "Destination ports at risk", len(port_risk), risk.tool,
                ", ".join(f"{p['portCode']} ({p['risk']:.2f})" for p in worst),
                unit="ports",
            ))

        divertible = len({r["vesselId"] for r in actionable})
        locked = len({r["vesselId"] for r in committed})
        summary = (
            f"{len(exposed)} of {risk.result.get('fleetSize', 0)} vessels are exposed "
            f"over {request.horizon_hours:.0f} h. "
            f"{divertible} can still be rerouted; "
            f"{locked} {'is' if locked == 1 else 'are'} already committed."
        )
        return _assemble(self, calls, findings, summary,
                         {"rows": rows, "portRisk": port_risk})


# --------------------------------------------------------------------------
# Port twin
# --------------------------------------------------------------------------


class PortTwinAgent(Agent):
    name = "port_twin"
    purpose = "Report the port's operating state and how it evolves under a policy."
    allowed_tools = (
        "portwatch.ports.get", "portwatch.port_twin.state",
        "portwatch.port_twin.simulate",
    )
    max_access = SIMULATE
    failure_modes = (
        "No observed snapshot exists for the port.",
        "The twin's geometry is schematic; positions carry no survey authority.",
    )

    def run(self, request: AgentRequest) -> AgentResult:
        calls: List[ToolCall] = []
        findings: List[Finding] = []
        if not request.port_code:
            return _assemble(self, calls, findings,
                             "No port was named, so no twin could be built.")

        snapshot = self.call(
            "portwatch.ports.get", {"port_code": request.port_code}, trace=calls
        )
        simulated = self.call(
            "portwatch.port_twin.simulate",
            {"port_code": request.port_code, "policy": "greedy",
             "horizon_hours": min(request.horizon_hours, 24.0)},
            trace=calls,
        )

        if snapshot.ok:
            row = snapshot.result
            for label, key, unit in (
                ("Congestion index", "congestionIndex", None),
                ("Delay", "delayHours", "h"),
                ("Vessels at anchorage", "anchorageCount", "vessels"),
                ("Queue pressure", "queuePressure", "index"),
            ):
                if row.get(key) is not None:
                    findings.append(Finding(label, row[key], snapshot.tool,
                                            f"Observed at {row.get('observedAt', 'unknown')}.",
                                            unit=unit))

        if simulated.ok:
            metrics = simulated.result.get("metrics", {})
            findings.append(Finding(
                "Berth utilisation", metrics.get("berthUtilisation"), simulated.tool,
                "At the end of the simulated horizon.", unit="fraction",
            ))
            findings.append(Finding(
                "Yard utilisation", metrics.get("yardUtilisation"), simulated.tool,
                f"{metrics.get('yardOverflowBlocks', 0)} blocks above 95%.",
                unit="fraction",
            ))
            if metrics.get("meanWaitHours") is not None:
                findings.append(Finding(
                    "Mean wait", metrics["meanWaitHours"], simulated.tool,
                    "Simulated, under the greedy scheduling policy.", unit="h",
                ))
            findings.append(Finding(
                "Geometry basis", simulated.result.get("geometryBasis"), simulated.tool,
                "Berth and yard positions are schematic, not a surveyed port plan.",
            ))

        summary = (
            f"{request.port_code}: "
            + (
                f"congestion {snapshot.result.get('congestionIndex')}, "
                f"{snapshot.result.get('anchorageCount')} at anchorage"
                if snapshot.ok else "no observed state"
            )
            + (
                f"; simulated berth utilisation "
                f"{simulated.result.get('metrics', {}).get('berthUtilisation')}"
                if simulated.ok else ""
            )
        )
        return _assemble(self, calls, findings, summary, {
            "snapshot": snapshot.result if snapshot.ok else None,
            "simulation": simulated.result if simulated.ok else None,
        })


# --------------------------------------------------------------------------
# Route, cargo, scenario, learning
# --------------------------------------------------------------------------


class RouteAgent(Agent):
    name = "route"
    purpose = "Score a vessel's routing against event, weather and port exposure."
    allowed_tools = ("portwatch.routing.optimize",)
    max_access = SIMULATE
    failure_modes = (
        "The vessel is not in the configured fleet.",
        "Routing geometry is non-navigational and is never a passage plan.",
    )

    def run(self, request: AgentRequest) -> AgentResult:
        calls: List[ToolCall] = []
        findings: List[Finding] = []
        if not request.vessel_id:
            return _assemble(self, calls, findings,
                             "No vessel was named, so no routing could be scored.")

        call = self.call(
            "portwatch.routing.optimize",
            {"vessel_id": request.vessel_id,
             "risk_tolerance": request.context.get("riskTolerance", "medium")},
            trace=calls,
        )
        if not call.ok:
            return _assemble(self, calls, findings,
                             f"Routing could not be scored for {request.vessel_id}.")

        row = call.result
        findings.append(Finding("Lane", row.get("lane"), call.tool,
                                f"{row.get('primaryRoutingNm')} nm on the primary routing.",
                                unit="nm"))
        if row.get("detourNm") is not None:
            findings.append(Finding(
                "Diversion cost", row.get("detourHours"), call.tool,
                f"Via {row.get('alternativeRouting')}, {row.get('detourNm')} nm further.",
                unit="h",
            ))
        else:
            findings.append(Finding(
                "Alternative routing", "none", call.tool,
                "This lane has no alternative in the catalogue. Disruption cannot be "
                "routed around.",
            ))
        findings.append(Finding("Worst exposure", row.get("worstExposure"), call.tool,
                                f"Threshold for this risk tolerance: {row.get('threshold')}.",
                                unit="index"))
        findings.append(Finding("Recommendation", row.get("recommendation"), call.tool,
                                row.get("note", "")))

        return _assemble(
            self, calls, findings,
            f"{row.get('vesselName')} on {row.get('lane')}: {row.get('recommendation')} "
            f"(worst exposure {row.get('worstExposure')}).",
            {"routing": row},
        )


class CargoAgent(Agent):
    name = "cargo"
    purpose = "Find and rank feasible transshipment connections at a port."
    allowed_tools = ("portwatch.cargo.opportunities", "portwatch.cargo.optimize")
    max_access = SIMULATE
    failure_modes = (
        "No commercial manifest feed is connected; the manifest is schematic demo data.",
        "No observed snapshot exists for the port.",
    )

    def run(self, request: AgentRequest) -> AgentResult:
        calls: List[ToolCall] = []
        findings: List[Finding] = []
        if not request.port_code:
            return _assemble(self, calls, findings, "No port was named.")

        plan = self.call(
            "portwatch.cargo.optimize", {"port_code": request.port_code}, trace=calls
        )
        if not plan.ok:
            return _assemble(self, calls, findings,
                             f"No cargo plan could be produced for {request.port_code}.")

        row = plan.result
        findings.append(Finding("Connections placed", row.get("placedCount"), plan.tool,
                                f"{row.get('totalTeu')} TEU assigned to onward sailings.",
                                unit="shipments"))
        findings.append(Finding("Unplaced", row.get("unplacedCount"), plan.tool,
                                "Each carries the reason it could not be connected.",
                                unit="shipments"))
        if row.get("foregoneValue"):
            findings.append(Finding(
                "Value foregone", row.get("foregoneValue"), plan.tool,
                "Capacity ran out before these shipments were reached. This is the "
                "measurable gap between the greedy plan and a better one.",
            ))
        top = (row.get("assignments") or [])[:1]
        if top:
            findings.append(Finding(
                "Best connection", top[0]["vesselName"], plan.tool, top[0]["rationale"],
            ))
        findings.append(Finding("Data basis", "schematic", plan.tool,
                                row.get("disclaimer", "")))

        return _assemble(
            self, calls, findings,
            f"{row.get('placedCount')} of "
            f"{row.get('placedCount', 0) + row.get('unplacedCount', 0)} transshipment "
            f"shipments have a feasible connection at {request.port_code}.",
            {"plan": row},
        )


class ScenarioAgent(Agent):
    name = "scenario"
    purpose = "Propagate a shock through the port network and report the deltas."
    allowed_tools = ("portwatch.scenarios.simulate",)
    max_access = SIMULATE
    failure_modes = ("The forecast artefact has not been exported.",)

    def run(self, request: AgentRequest) -> AgentResult:
        calls: List[ToolCall] = []
        findings: List[Finding] = []
        shock = request.context.get("shockType", "chokepoint_closure")
        call = self.call(
            "portwatch.scenarios.simulate",
            {"shock_type": shock,
             "severity": request.context.get("severity", 0.7),
             "chokepoint": request.context.get("chokepoint")},
            trace=calls,
        )
        if not call.ok:
            return _assemble(self, calls, findings, "No scenario could be run.")

        row = call.result
        ports = row.get("ports", [])
        findings.append(Finding("Ports affected", len(ports), call.tool,
                                row.get("method", ""), unit="ports"))
        if ports:
            findings.append(Finding(
                "Worst delta", ports[0]["deltaCongestion"], call.tool,
                f"{ports[0]['portCode']}: "
                f"{ports[0]['baselineCongestion']} -> {ports[0]['shockedCongestion']}.",
                unit="index",
            ))
        return _assemble(
            self, calls, findings,
            f"A {shock} shock moves congestion at {len(ports)} ports"
            + (f", worst at {ports[0]['portCode']}." if ports else "."),
            {"scenario": row},
        )


class OutcomeReportAgent(Agent):
    name = "outcome"
    purpose = "Report how past claims scored, and what the system changed as a result."
    allowed_tools = (
        "portwatch.learning.outcomes", "portwatch.learning.reliability",
        "portwatch.learning.policies",
    )
    max_access = READ
    failure_modes = (
        "No claim has resolved yet, in which case calibration is reported as "
        "unavailable rather than perfect.",
    )

    def run(self, request: AgentRequest) -> AgentResult:
        calls: List[ToolCall] = []
        findings: List[Finding] = []

        outcomes = self.call("portwatch.learning.outcomes", {"limit": 5}, trace=calls)
        reliability = self.call("portwatch.learning.reliability", {}, trace=calls)
        policies = self.call("portwatch.learning.policies", {}, trace=calls)

        if outcomes.ok:
            overall = outcomes.result.get("overall", {})
            continuous = overall.get("continuous") or {}
            events = outcomes.result.get("events", {})
            findings.append(Finding("Resolved claims", overall.get("count"), outcomes.tool,
                                    "Predictions with an observation attached.",
                                    unit="claims"))
            if continuous.get("meanAbsoluteError") is not None:
                findings.append(Finding(
                    "Mean absolute error", continuous["meanAbsoluteError"], outcomes.tool,
                    f"Interval coverage {continuous.get('intervalCoverage')} against a "
                    f"nominal {continuous.get('nominalCoverage')}.",
                ))
            if events.get("available"):
                findings.append(Finding(
                    "Event Brier score", events.get("overall", {}).get("brier"),
                    outcomes.tool,
                    f"Skill against the base rate: "
                    f"{events.get('overall', {}).get('brierSkill')}.",
                ))
            else:
                findings.append(Finding(
                    "Event calibration", "unavailable", outcomes.tool,
                    events.get("note", "No event claim has reached its horizon yet."),
                ))

        if reliability.ok:
            rows = reliability.result
            moved = [r for r in rows if r.get("previousWeight") is not None
                     and abs(r["weight"] - r["previousWeight"]) > 0.001]
            findings.append(Finding("Reliability weights", len(rows), reliability.tool,
                                    f"{len(moved)} changed at the last recalibration.",
                                    unit="weights"))

        if policies.ok:
            findings.append(Finding(
                "Approved policy", policies.result.get("activePolicyId") or "none",
                policies.tool, policies.result.get("note", ""),
            ))

        return _assemble(
            self, calls, findings,
            "Learning state reported from the outcome ledger.",
            {
                "outcomes": outcomes.result if outcomes.ok else None,
                "reliability": reliability.result if reliability.ok else None,
                "policies": policies.result if policies.ok else None,
            },
        )


class AdvisoryAgent(Agent):
    name = "advisory"
    purpose = (
        "Draft a port-to-vessel advisory from computed evidence, for a controller "
        "to review. It cannot issue one."
    )
    allowed_tools = (
        "portwatch.advisories.list", "portwatch.advisories.draft",
        "portwatch.port_twin.simulate",
    )
    #: PROPOSE, never EXECUTE. This is the highest access any agent holds, and
    #: the registry refuses anything above it even if this constant changed.
    max_access = PROPOSE
    failure_modes = (
        "The advisory is not well formed and the store refuses it.",
        "A draft is never visible to the recipient; only a controller can issue it.",
    )

    def run(self, request: AgentRequest) -> AgentResult:
        calls: List[ToolCall] = []
        findings: List[Finding] = []

        existing = self.call(
            "portwatch.advisories.list",
            {"port_code": request.port_code, "vessel_id": request.vessel_id},
            trace=calls, scope=request.scope,
        )
        if existing.ok:
            open_rows = [
                a for a in existing.result
                if a["state"] in ("draft", "under_review", "issued", "acknowledged")
            ]
            findings.append(Finding("Open advisories", len(open_rows), existing.tool,
                                    "Already in the register for this scope.",
                                    unit="advisories"))

        draft = request.context.get("draft")
        if not draft:
            return _assemble(
                self, calls, findings,
                "No computed recommendation was supplied, so no advisory was drafted. "
                "An advisory must carry a number a model produced; this agent will not "
                "invent one.",
            )

        created = self.call("portwatch.advisories.draft", draft, trace=calls)
        if created.ok:
            findings.append(Finding("Draft raised", created.result["advisoryId"],
                                    created.tool, created.result.get("note", "")))
            findings.append(Finding("Visible to recipient", False, created.tool,
                                    "A draft stays inside the port authority until a "
                                    "named controller reviews and issues it."))

        return _assemble(
            self, calls, findings,
            (
                f"Draft {created.result['advisoryId']} raised for review."
                if created.ok else "No advisory could be drafted."
            ),
            {"draft": created.result if created.ok else None},
        )


SPECIALISTS: Dict[str, type] = {
    cls.name: cls
    for cls in (
        GlobalEyeAgent, WeatherAgent, FleetAgent, PortTwinAgent,
        RouteAgent, CargoAgent, ScenarioAgent, OutcomeReportAgent, AdvisoryAgent,
    )
}


__all__ = [
    "SPECIALISTS",
    "AdvisoryAgent",
    "CargoAgent",
    "FleetAgent",
    "GlobalEyeAgent",
    "OutcomeReportAgent",
    "PortTwinAgent",
    "RouteAgent",
    "ScenarioAgent",
    "WeatherAgent",
]
