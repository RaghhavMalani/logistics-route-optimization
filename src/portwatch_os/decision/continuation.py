"""Rehydrate visitor weather decisions without reranking their frozen evidence."""
from dataclasses import fields
import copy
from . import model as m


def _camel(name):
    first, *rest = name.split("_")
    return first + "".join(part.title() for part in rest)


def _read(cls, body, **overrides):
    values = {f.name: copy.deepcopy(body[_camel(f.name)]) for f in fields(cls)
              if _camel(f.name) in body}
    values.update(overrides)
    return cls(**values)


def restore(body):
    options = []
    for row in body["options"]:
        evaluation = row.get("evaluation")
        if evaluation:
            evaluation = _read(m.DecisionEvaluation, evaluation, objectives={
                key: _read(m.Measure, value) for key, value in evaluation["objectives"].items()})
        options.append(_read(m.DecisionOption, row, evaluation=evaluation,
            availability=_read(m.Availability, row["availability"]),
            constraints=[_read(m.ConstraintResult, c) for c in row["constraints"]]))
    subject = body["subject"]
    result = _read(m.DecisionProblem, body,
        subject_type=subject["type"], subject_id=subject["id"], subject_label=subject["label"],
        actor=_read(m.DecisionActor, body["actor"], vessel_ids=tuple(body["actor"].get("vesselIds") or [])),
        objectives=[_read(m.DecisionObjective, row) for row in body["objectives"]], options=options,
        frontier=_read(m.DecisionFrontier, body["frontier"]) if body.get("frontier") else None,
        recommendation=_read(m.DecisionRecommendation, body["recommendation"]) if body.get("recommendation") else None)
    if result.validate():
        raise m.DecisionError("Invalid saved comparison: " + "; ".join(result.validate()))
    return result


def connected_basis(problem):
    return problem.evidence.get("currentEnvironment") or problem.evidence.get("intelligenceBasis")


def require_current(problem):
    """Only inputs consumed by this gate matter; ambient news revisions do not."""
    from datetime import timedelta
    from fastapi import HTTPException
    from src.portwatch_os.clock import get_clock, LIVE, wall_now
    from src.portwatch_os.intelligence.current_environment import instant
    from src.portwatch_os.sandbox import current_sandbox
    scoped = current_sandbox.get()
    env = connected_basis(problem)
    reason = None
    if get_clock().state.mode != LIVE:
        reason = "Return to the live clock before continuing this frozen comparison."
    elif instant(env["plannedArrival"]) <= wall_now() or wall_now()-instant(env["availableAt"]) > timedelta(hours=1):
        reason = "The frozen input receipt or requested arrival has expired."
    elif scoped:
        vessel = next((v for v in scoped.world["fleet"] if v["id"] == problem.subject_id), None)
        from backend.app.services.demo_terminal import company_for
        current = company_for(scoped.world).vessel(problem.subject_id)
        if not vessel or vessel["portCode"] != env["portCode"] or not current or instant(current.eta) != instant(env["earliestVoyageArrival"]):
            reason = "The consumed voyage destination or declared ETA has changed."
        if not reason and env.get('kind') == 'NOTICE_RESTRICTION':
            if (vessel.get('declaredPassage') or {}).get('id') != env['restriction']['plan']['id']:
                reason = 'The consumed route, characteristics or passage declaration has changed.'
            elif instant(env['restriction']['plan']['passageAt']) <= wall_now():
                reason = 'The declared lock passage is no longer future.'
            else:
                from src.portwatch_os.intelligence.operational_notices import require_revision
                try: require_revision(env)
                except ValueError as exc: reason = str(exc)
    if reason:
        raise HTTPException(409, reason + " Company can explicitly refresh to a linked successor; this comparison and its approvals remain saved.")


def weather_explanation(problem):
    """The closure-duration stress policy does not apply to this approach gate."""
    rec = problem.recommendation
    if rec is None:
        return
    rec.policy = "forecast-approach-comparison-v1"
    rec.why = ("Both options reach the same forecast-clear approach time. Later requested arrival reduces assumed anchorage waiting; overall port access is unchanged. "
               "Gust and visibility forecasts and operator limits drive this comparison. GDACS is regional context. "
               "Fuel, cost, berth availability and calibrated uncertainty are unavailable; this is not a measured saving.")
    rec.statement = rec.why
    rec.robustness = None


def intelligence_explanation(problem):
    rec=problem.recommendation
    if rec is None: return
    if problem.evidence['intelligenceBasis'].get('kind') == 'NOTICE_RESTRICTION':
        rec.policy='authority-scheduled-access-v1'
        rec.why=('The declared Eastham passage overlaps the authority’s explicit lock closure. '
            'Both options use the same first published operational tide and conditional destination arrival. '
            'Revising the request reduces planned waiting at the lock; it does not shorten total delivery time. '
            'Queen Elizabeth II Lock is unaffected, but alternative suitability/booking and actual lock access are unavailable. '
            'Fuel, cost, berth, clearance and safety benefits are unavailable.')
        rec.statement=rec.why;rec.robustness=None
        return
    rec.policy="intelligence-review-scenario-v1"
    rec.why=("Reported facts identify a subject for review; destination/lane exposure is inferred. "
        "The alternative changes declared arrival by an explicit operator-assumed hold, not an estimated event-caused delay. "
        "No calibrated safety, fuel, cost, berth or access benefit is established. Review the source validity and assumptions before choosing.")
    rec.statement=rec.why;rec.robustness=None
