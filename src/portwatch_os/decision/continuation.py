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
        episode = env.get('operationalEpisode')
        if episode and (vessel or {}).get('operationalEpisode', {}).get('id') != episode['id']:
            reason = 'This comparison belongs to another operational call; start a comparison for the current call.'
        elif not vessel or vessel["portCode"] != env["portCode"] or not current or instant(current.eta) != instant(env["earliestVoyageArrival"]):
            reason = "The consumed voyage destination or declared ETA has changed."
            if vessel and current:
                reason += (f" Frozen {env['portCode']} arrival {env['earliestVoyageArrival']};"
                           f" current {vessel['portCode']} arrival {current.eta}.")
        if not reason and env.get('kind') == 'NOTICE_RESTRICTION':
            from src.portwatch_os.intelligence.voyage_exposure import passage_for
            declared=passage_for(vessel,env['restriction']['plan'].get('areaId')) or {}
            if declared.get('id') != env['restriction']['plan']['id']:
                reason = 'The consumed route, characteristics or passage declaration has changed.'
            elif instant(env['restriction']['plan']['passageAt']) <= wall_now():
                reason = 'The declared lock passage is no longer future.'
            else:
                if env['restriction'].get('sourceFamily')=='NAVCEN_MSI':
                    from src.portwatch_os.intelligence.navigation_restrictions import require_revision
                else:
                    from src.portwatch_os.intelligence.operational_notices import require_revision
                try: require_revision(env)
                except ValueError as exc: reason = str(exc)
        if not reason and env.get("cargoCommitment"):
            from .passage_cargo_integration import require_cargo_current
            reason = require_cargo_current(env, scoped)
    if not reason and env.get('feedbackConsumption'):
        from src.portwatch_os.learning import intelligence_reconciliation as collector
        from src.portwatch_os.learning.shared_feedback import require_consumption
        public = collector.open_public()
        try:
            from backend.app.routes.shared_feedback import require_originals
            require_originals(env['feedbackConsumption'])
            require_consumption(public, env['feedbackConsumption'])
        except ValueError as exc:
            reason = str(exc)
        finally:
            public.close()
    if reason:
        raise HTTPException(409, reason + " Company can explicitly refresh to a linked successor; this comparison and its approvals remain saved.")


def weather_explanation(problem):
    """The closure-duration stress policy does not apply to this approach gate."""
    rec = problem.recommendation
    if rec is None:
        return
    environment = problem.evidence.get("currentEnvironment") or {}
    if environment.get("passagePlan"):
        chosen = problem.option(rec.option_id)
        derived = chosen.evaluation.derived if chosen and chosen.evaluation else {}
        ranking = rec.ranking_basis or {}
        used = ", ".join(ranking.get("objectivesUsed") or []) or "none"
        dropped = ", ".join(ranking.get("objectivesDropped") or []) or "none"
        rec.policy = "declared-passage-comparison-v1"
        rec.why = (
            ("Keep the current declared passage plan. " if chosen and chosen.is_baseline else
             "Conditional passage alternative for Company and Vessel review. ")
            + f"Selected approach arrival {derived.get('arrivalAt', 'unavailable')}; "
              f"conditional clear approach {derived.get('approachClearAt', 'unavailable')}. "
              "Each option uses its own sailing time and relevant hourly gust/visibility forecasts under the frozen operator limits. "
              f"Existing ranking objectives used: {used}; dropped or unavailable: {dropped}. "
              "Fuel and monetary components are modeled only where their displayed quantities, consumption assumptions and applicable rates support them; partial costs are not total savings. "
              "The Port reviews an advisory proposal and does not command navigation. GDACS remains regional context. "
              "No measured saving, berth availability, whole-route safety or official clearance is established."
        )
        rec.statement = rec.why
        if environment.get("cargoCommitment"):
            assessment = derived.get("cargoAssessment") or {}
            rec.why += (" Cargo connection: " + str(assessment.get("status", "UNKNOWN")) + ". "
                + ("The explicitly required commitment constrains passage eligibility. " if environment["cargoCommitment"].get("mustMeet")
                   else "Optional cargo context does not change passage eligibility or ranking. ")
                + "Conditional handling uses declared downstream assumptions; no booking, berth access, cargo release or final delivery is confirmed.")
            rec.statement = rec.why
        rec.robustness = None
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
        if problem.evidence['intelligenceBasis']['restriction'].get('sourceFamily')=='NAVCEN_MSI':
            rec.why=('The declared passage requires a bridge opening during the published closed-position interval. '
                'Both options reach the same conditional bridge access and destination arrival. '
                'Revising requested passage relocates planned bridge waiting, without faster delivery. '
                'The local zone is an explicitly confirmed geographic assumption; actual opening, water level, clearance, '
                'route suitability and berth timing are unavailable. Fuel, cost, safety and capacity benefits are unavailable.')
            rec.statement=rec.why;rec.robustness=None
            return
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
