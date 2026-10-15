"""Typed source claims and operational targets using the existing durable ledger.

Facts are not probabilistic forecasts. Missing evidence is never a negative
observation. Resolved numerical targets use the existing Outcome Agent.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math

from src.portwatch_os.ledger.schema import PredictionRecord, PredictionContext, CONTINUOUS
from src.portwatch_os.learning.outcome_agent import OutcomeAgent
from src.portwatch_os.learning.reliability import fit_reliability, MIN_SAMPLES_TO_APPLY

FX_UNIT = "INR/USD"
FX_AGGREGATION = "NEW_YORK_NOON_BUYING_RATE"
CLAIM_KINDS = {"REPORTED_FACT", "FORECAST", "INFERRED_EXPOSURE", "OPERATOR_ASSUMPTION"}


def instant(value):
    at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if not at.tzinfo:
        raise ValueError("Explicit timezone required")
    return at.astimezone(timezone.utc)


def identifier(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, allow_nan=False).encode()).hexdigest()


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def claim(store, body):
    required = ("kind", "wording", "entity", "geography", "originAt", "target", "firstAvailableAt",
                "source", "sourceVersion", "inputs", "eventKey", "independenceKey")
    if any(key not in body for key in required) or body["kind"] not in CLAIM_KINDS:
        raise ValueError("Explicit claim semantics required")
    instant(body["originAt"]); instant(body["firstAvailableAt"])
    if body["kind"] == "FORECAST":
        if instant(body["target"]["at"]) <= instant(body["originAt"]):
            raise ValueError("A forecast must be frozen before its future target")
        if any(instant(i["firstAvailableAt"]) > instant(body["originAt"]) for i in body["inputs"]):
            raise ValueError("Consumed input was unavailable at forecast origin")
    value = {**body, "id": identifier(body), "contractVersion": "shared-feedback-v1"}
    store.append_feedback("claim", value)
    return value


def news_report(store, *, wording, source, source_version, independence_key, event_key,
                entity, geography, target, first_available_at, published_at, response_sha256, value=True, unit="boolean"):
    """Explicit reviewed event identity joins syndicated reports, not their truth.

    Callers must supply an event/reference key and exact extracted wording.
    Headline similarity alone is deliberately not an event identity.
    """
    if target.get("kind") not in ("ANNOUNCEMENT", "ACTUAL_EVENT") or not event_key or not wording:
        raise ValueError("A specific reviewed news target and event reference are required")
    if not response_sha256 or len(response_sha256) != 64:
        raise ValueError("Retained original news response required")
    return claim(store, {"kind": "REPORTED_FACT", "wording": wording, "value": value,
        "entity": entity, "geography": geography, "originAt": first_available_at,
        "target": target, "firstAvailableAt": first_available_at, "publishedAt": published_at,
        "source": source, "sourceVersion": source_version, "responseSha256": response_sha256,
        "eventKey": event_key, "independenceKey": independence_key, "inputs": [],
        "unit": unit, "aggregation": "EXPLICIT_NEWS_TARGET"})


def evidence(store, body):
    for key in ("eventKey", "target", "entity", "geography", "source", "sourceVersion", "independenceKey",
                "firstAvailableAt", "observedAt", "unit", "aggregation", "value", "recordKind", "responseSha256"):
        if key not in body:
            raise ValueError("Outcome identity, source and availability required: " + key)
    if not body["responseSha256"] or len(body["responseSha256"]) != 64:
        raise ValueError("Retained source response required")
    if body["recordKind"] == "ACTUAL_OPERATIONAL_RECORD" and not body.get("independentTargetKey"):
        raise ValueError("Actual operational records require an independent voyage/operation target identity")
    instant(body["firstAvailableAt"]); instant(body["observedAt"])
    if instant(body["firstAvailableAt"]) < instant(body["observedAt"]):
        raise ValueError("Outcome cannot be available before observation")
    value = {**body, "id": identifier(body)}
    return store.append_feedback("evidence", value)


def verify_news(store, report, now):
    """Independent operator/authority evidence must address the exact target.

    ANNOUNCEMENT and ACTUAL_EVENT deliberately cannot settle each other.
    Cancellation changes applicability, not the truth of a past announcement.
    """
    candidates = [e for e in store.feedback("evidence") if e["eventKey"] == report["eventKey"]
                  and e["entity"] == report["entity"] and e["geography"] == report["geography"]
                  and instant(e["firstAvailableAt"]) <= instant(now)]
    matching = [e for e in candidates if e["target"] == report["target"]
                and e["unit"] == report.get("unit") and e["aggregation"] == report.get("aggregation")
                and e["recordKind"] in ("AUTHORITY_RECORD", "OPERATOR_RECORD")
                and e["independenceKey"] != report["independenceKey"]
                and e.get("derivedFrom") != report["independenceKey"]]
    latest = sorted(matching, key=lambda e: (instant(e["firstAvailableAt"]), e["id"]))
    # Contradictory independent records remain unresolved until explicitly revised.
    live = [e for e in latest if not any(x.get("supersedes") == e["id"] for x in latest)]
    verdicts = {"CORROBORATED" if e["value"] == report.get("value") else "CONTRADICTED" for e in live}
    verdict = verdicts.pop() if len(verdicts) == 1 else "UNRESOLVED"
    cancelled = [e for e in candidates if e["recordKind"] == "CANCELLATION"
                 and e.get("cancelsSourceVersion") == report["sourceVersion"]]
    body = {"claimId": report["id"], "eventKey": report["eventKey"], "verdict": verdict,
            "applicability": "SUPERSEDED" if cancelled else "AS_REPORTED",
            "evidenceIds": sorted(e["id"] for e in live + cancelled),
            "reason": "Independent evidence addresses the same target" if live else
                      "Independent authority/operator evidence unavailable; absence is not contradiction"}
    old = store.feedback("assessment", identifier(body))
    if old:
        return old[0]
    sequence = 1 + len([a for a in store.feedback("assessment") if a["claimId"] == report["id"]])
    return store.append_feedback("assessment", {**body, "id": identifier(body), "assessedAt": now, "sequence": sequence})


def current_assessment(store, item, as_of=None):
    rows = [a for a in store.feedback("assessment") if a["claimId"] == item["id"]
            and (as_of is None or instant(a["assessedAt"]) <= instant(as_of))]
    return max(rows, key=lambda a: (instant(a["assessedAt"]), a.get("sequence", 0))) if rows else None


def freeze_fx(store, quote, now, target_date=None):
    origin = instant(now)
    target = instant(target_date + "T16:00:00+00:00") if target_date else origin.replace(hour=16, minute=0, second=0, microsecond=0) + timedelta(days=1)
    while target.weekday() >= 5:
        target += timedelta(days=1)
    # This UTC time is a target-date label, not a claimed publication/market time.
    date = target.date().isoformat()
    existing = [c for c in store.feedback("claim") if c["target"].get("series") == "DEXINUS"
                and c["kind"] == "FORECAST" and c["target"]["date"] == date]
    if existing:
        return existing[0]
    if quote["unit"] != FX_UNIT or quote["aggregation"] != FX_AGGREGATION or not finite(quote["value"]):
        raise ValueError("A finite DEXINUS noon rate in INR per USD is required")
    item = claim(store, {"kind": "FORECAST", "wording": "Persistence forecast: next target-date DEXINUS equals the latest retained quote",
        "value": quote["value"], "unit": FX_UNIT, "aggregation": FX_AGGREGATION,
        "entity": "USD/INR", "geography": "India / New York reference rate", "originAt": now,
        "target": {"kind": "ECONOMIC_OBSERVATION", "series": "DEXINUS", "date": date, "at": target.isoformat(),
                   "timePrecision": "OBSERVATION_DATE_ONLY; UTC timestamp is an eligibility label"},
        "firstAvailableAt": now, "source": "PortWatch persistence baseline", "sourceVersion": "persistence-v1",
        "eventKey": "DEXINUS:" + date, "independenceKey": "PortWatch persistence baseline", "inputs": [quote],
        "releasePolicy": "Daily observations released weekly by Federal Reserve H.10; holiday delays and revisions possible",
        "missingDatePolicy": "No interpolation or carry-forward as outcome", "status": "COLLECTING",
        "baselineAgeDays": (origin-instant(quote["observedAt"])).days,
        "baselineStatus": "STALE" if (origin-instant(quote["observedAt"])).days > 7 else "RECENT_OBSERVATION"})
    register_prediction(store, item, "economic_persistence")
    return item


def register_prediction(store, item, model):
    if store.get_prediction(item["id"]):
        return
    value = item["value"]
    store.record_prediction(PredictionRecord(prediction_id=item["id"], domain="event" if model == "economic_persistence" else "route",
        kind=CONTINUOUS, target=item["target"]["kind"], subject=item["entity"], model=model,
        model_version="shared-feedback-v1", issued_at=item["originAt"], valid_at=item["target"]["at"],
        context=PredictionContext(region=item["geography"], horizon_hours=(instant(item["target"]["at"])-instant(item["originAt"])).total_seconds()/3600),
        predicted_value=value, features={model: value, "__persistence__": value},
        provenance={"feedbackClaimId": item["id"], "unit": item["unit"], "aggregation": item["aggregation"]}))


def reconcile(store, now):
    claims = {c["id"]: c for c in store.feedback("claim") if c["kind"] == "FORECAST"}
    outcomes = store.feedback("evidence")
    def observe(row):
        item = claims.get(row.prediction_id)
        if not item:
            return None
        allowed = [e for e in outcomes if e["entity"] == item["entity"] and e["geography"] == item["geography"]
                   and e["unit"] == item["unit"] and e["aggregation"] == item["aggregation"]
                   and e["recordKind"] in ("ECONOMIC_OBSERVATION", "ACTUAL_OPERATIONAL_RECORD")
                   and instant(item["originAt"]) < instant(e["firstAvailableAt"]) <= instant(now)
                   and instant(e["observedAt"]) > instant(item["originAt"]) and finite(e["value"])]
        if item["target"]["kind"] != "ECONOMIC_OBSERVATION":
            selected = store.feedback("selected-impact", item["id"])
            if not selected or not item.get('operationalEpisode'):
                return None
            allowed = [e for e in allowed if operational_record_matches(e, item)
                       and execution_cutoff(e, item, selected[0])]
            if len({instant(e['forecastCutoffAt']) for e in allowed}) > 1:
                return None
        else:
            allowed = [e for e in allowed if e['recordKind']=='ECONOMIC_OBSERVATION'
                       and e['eventKey'] == item['eventKey'] and e['target'] == item['target']]
        if not allowed:
            return None
        first = min(allowed, key=lambda e: (instant(e["firstAvailableAt"]), e["id"]))
        store.append_feedback("match", {"id": item["id"], "claimId": item["id"], "evidenceId": first["id"],
                                          "availableAt": first["firstAvailableAt"], "scoringVintage": "FIRST_RETAINED_OUTCOME"})
        return first["value"], first["firstAvailableAt"], first["source"]
    return OutcomeAgent(store, observer=observe).resolve_due(now=now)


def execution_cutoff(record, item, selection):
    """An actual log must name execution and the forecast cutoff, not approval."""
    try:
        cutoff = instant(record['forecastCutoffAt'])
        executed = instant(record['executedAt'])
        return (instant(item['originAt']) <= instant(item['firstAvailableAt'])
                <= instant(selection['selectedAt']) <= cutoff <= executed <= instant(record['observedAt'])
                and selection.get('operationalActionId') == item.get('operationalActionId'))
    except (KeyError, ValueError, TypeError):
        return False


def operational_record_matches(record, item):
    """The operation, executed action and measured quantity must all agree.

    Old records with only an episode/metric label remain inspectable but cannot
    verify a new prediction whose baseline and measurement scope are explicit.
    """
    episode = item.get('operationalEpisode') or {}
    if not finite(record.get('value')):
        return False
    if item['target']['kind'] == 'WAITING' and record['value'] < 0:
        return False
    if item['target']['kind'] in ('WAITING','SCHEDULE_SHIFT'):
        basis=item.get('metricBasis') or {}
        reference=basis.get('requestedAccessAt') if item['target']['kind']=='WAITING' else basis.get('referenceArrivalAt')
        try:
            measurement=instant(reference)+timedelta(hours=record['value'])
            if not instant(record['executedAt']) <= measurement <= instant(record['observedAt']):
                return False
        except (KeyError,ValueError,TypeError,OverflowError):
            return False
    if item['target']['kind'] == 'ACCESS_TIME':
        try:
            if not (instant(record['executedAt']).timestamp() <= record['value']
                    <= instant(record['observedAt']).timestamp()):
                return False
        except (KeyError, ValueError, TypeError):
            return False
    return bool(item.get('actionBasisSha256') and item.get('metricBasisSha256')
        and record.get('recordKind') == 'ACTUAL_OPERATIONAL_RECORD'
        and record.get('entity') == item['entity'] and record.get('geography') == item['geography']
        and record.get('unit') == item['unit'] and record.get('aggregation') == item['aggregation']
        and record.get('independentTargetKey') == item.get('independentTargetKey')
        and record.get('episodeId') == episode.get('id')
        and record.get('executedActionId') == item.get('operationalActionId')
        and record.get('actionBasisSha256') == item['actionBasisSha256']
        and record.get('metricBasisSha256') == item['metricBasisSha256']
        and record.get('target', {}).get('kind') == item['target']['kind'])


def reliability_version(store, now):
    """Independent cohorts; descriptive reliability, no automatic promotion.

    Revisions remain visible but revised targets are excluded from fitting.
    A persistence baseline cannot demonstrate improvement over itself.
    """
    groups = {}; independent = {}; candidates = {}; exclusions = []
    for item in store.feedback("claim"):
        row = store.get_prediction(item["id"])
        if not row or row.status != "resolved" or instant(row.observed_at) >= instant(now):
            continue
        operational = item['target']['kind'] != 'ECONOMIC_OBSERVATION'
        if operational and not item.get('operationalEpisode'):
            exclusions.append({'claimId':item['id'], 'reason':'Legacy target lacks a stable call and executed-action identity'})
            continue
        matches = [e for e in store.feedback("evidence") if e["eventKey"] == item["eventKey"]
                   and e["target"] == item["target"] and e["unit"] == item.get("unit")
                   and e["entity"] == item["entity"] and e["geography"] == item["geography"]
                   and e["aggregation"] == item.get("aggregation")
                   and e["recordKind"] == ("ACTUAL_OPERATIONAL_RECORD" if operational else "ECONOMIC_OBSERVATION")
                   and instant(e["firstAvailableAt"]) < instant(now)]
        if operational:
            selected = store.feedback('selected-impact', item['id'])
            matches = [e for e in store.feedback('evidence') if operational_record_matches(e, item)
                       and selected and execution_cutoff(e, item, selected[0])
                       and finite(e['value']) and instant(e['firstAvailableAt']) < instant(now)]
            if not matches:
                exclusions.append({'claimId': item['id'], 'reason': 'Actual measurement basis or executed action unavailable'})
                continue
            if len({instant(e['forecastCutoffAt']) for e in matches}) != 1:
                exclusions.append({'claimId': item['id'], 'reason': 'Conflicting executed-action forecast cutoffs'})
                continue
        if len({e["value"] for e in matches}) > 1:
            exclusions.append({'claimId': item['id'], 'reason': 'Revised or conflicting actual values; originals preserved'})
            continue
        cohort = (item["entity"], item["geography"], row.model, item.get("unit"), item.get("aggregation"), item["target"]["kind"])
        key = cohort + (item.get("independentTargetKey") or json.dumps(item["target"], sort_keys=True),)
        candidates.setdefault(key, []).append((item, row))
    # Explicit policy: latest approved forecast available by the executed log's
    # cutoff. Company/Port copies of that vintage have the same value and basis.
    # No database insertion order participates in the evaluation.
    for key, rows in candidates.items():
        if rows[0][0]['target']['kind'] == 'ECONOMIC_OBSERVATION':
            independent[key] = min(rows, key=lambda x:x[0]['id'])[1]
            continue
        cutoffs = set()
        for item, row in rows:
            match = store.feedback('match', item['id'])
            record = store.feedback('evidence', match[0]['evidenceId']) if match else []
            if record:
                cutoffs.add(instant(record[0]['forecastCutoffAt']))
        if len(cutoffs) != 1:
            exclusions.append({'independentTargetKey':key[-1], 'reason':'Conflicting executed-action forecast cutoffs'})
            continue
        if len({item['operationalActionId'] for item, row in rows}) != 1:
            exclusions.append({'independentTargetKey': key[-1], 'reason': 'Multiple executed actions for one episode metric; final action unresolved'})
            continue
        if len({item['metricBasisSha256'] for item, row in rows}) != 1:
            exclusions.append({'independentTargetKey': key[-1], 'reason': 'Conflicting measurement bases for one episode metric'})
            continue
        latest_origin = max(instant(item['originAt']) for item, row in rows)
        vintage = [(item,row) for item,row in rows if instant(item['originAt']) == latest_origin]
        if len({(item['predictionVintageId'], row.predicted_value) for item,row in vintage}) != 1:
            exclusions.append({'independentTargetKey':key[-1], 'reason':'Conflicting forecast vintages at the same cutoff origin'})
            continue
        independent[key] = min(vintage, key=lambda x:(x[0].get('representation') != 'COMPANY_SOURCE', x[0]['id']))[1]
    for key, row in independent.items():
        groups.setdefault(key[:-1], []).append(row)
    slices = []
    for cohort, rows in sorted(groups.items()):
        fitted = fit_reliability(rows, as_of=now)
        global_weight = next((r for r in fitted if r.context_key == "global"), None)
        slices.append({"context": list(cohort), "independentTargets": len(rows),
                       "bias": sum(r.error for r in rows)/len(rows),
                       "meanAbsoluteError": sum(r.absolute_error for r in rows)/len(rows),
                       "fittedWeight": global_weight.weight if global_weight else 1,
                       "consumedWeight": 1, "status": "COLLECTING",
                       "reason": "Chronological held-out improvement and calibration required before applying learning"})
    news_groups = {}
    for item in store.feedback("claim"):
        if item["kind"] != "REPORTED_FACT" or item["target"]["kind"] not in ("ANNOUNCEMENT", "ACTUAL_EVENT"):
            continue
        assessment = current_assessment(store, item, as_of=now)
        if assessment and instant(assessment["assessedAt"]) <= instant(now):
            key = (item["independenceKey"], item["entity"], item["target"]["kind"])
            target_key = (item["eventKey"], json.dumps(item["target"], sort_keys=True))
            news_groups.setdefault(key, {})[target_key] = assessment
    news_slices = []
    for context, targets in sorted(news_groups.items()):
        resolved = [a for a in targets.values() if a["verdict"] in ("CORROBORATED", "CONTRADICTED")]
        news_slices.append({"context": list(context), "independentTargets": len(resolved),
            "pendingTargets": len(targets)-len(resolved), "corroborated": sum(a["verdict"] == "CORROBORATED" for a in resolved),
            "contradicted": sum(a["verdict"] == "CONTRADICTED" for a in resolved), "status": "COLLECTING",
            "meaning": "Descriptive target agreement; not probability calibration or a shipping-delay score"})
    body = {"contractVersion": "shared-feedback-v1", "status": "COLLECTING", "consumedWeight": 1,
            "correction": None, "minimumSamplesForReliability": MIN_SAMPLES_TO_APPLY,
            "slices": slices, "newsSlices": news_slices, "sampleIds": sorted(r.prediction_id for r in independent.values()),
            "errorConvention": "observed minus predicted", "scope": "Source accuracy and shipping impact scored separately"}
    body['operationalSelectionPolicy'] = 'LATEST_APPROVED_FORECAST_BEFORE_EXECUTED_LOG_CUTOFF_V1'
    body['excludedTargets'] = exclusions
    old = store.feedback("version", identifier(body))
    if old:
        return old[0]
    return store.append_feedback("version", {**body, "id": identifier(body), "createdAt": now})


def inspect(store, now):
    items = []
    for item in store.feedback("claim"):
        row = store.get_prediction(item["id"])
        assessment = current_assessment(store, item)
        match = store.feedback("match", item["id"])
        outcomes = [e for e in store.feedback("evidence") if e["eventKey"] == item["eventKey"] and e["target"] == item["target"]]
        items.append({**item, "verification": assessment, "outcomes": outcomes, "match": match[0] if match else None,
                      "sourceQuality": next(iter(store.feedback("news-source-quality", item["id"])), None),
                      "score": {"status": row.status, "observed": row.observed_value, "error": row.error,
                                "absoluteError": row.absolute_error, "availableAt": row.observed_at} if row else None})
    news = [i for i in items if i["target"]["kind"] in ("ANNOUNCEMENT", "ACTUAL_EVENT")]
    events = []
    for key in sorted({i["eventKey"] for i in news}):
        reports = [i for i in news if i["eventKey"] == key]
        events.append({"id": key, "reportIds": [r["id"] for r in reports],
                       "sourceIds": sorted({r["independenceKey"] for r in reports}),
                       "targets": [r["target"] for r in reports]})
    return {"contractVersion": "shared-feedback-v1", "claims": sorted(items, key=lambda i: i["originAt"], reverse=True)[:100],
            "events": events,
            "reliability": reliability_version(store, now),
            "newsIndependentEvents": len({i["eventKey"] for i in news}),
            "newsSourceReports": len(news), "note": "Unresolved reports and absent outcomes remain pending. Simulation never verifies a real claim."}


def freeze_consumption(public_store, visitor_store, claim_ids, now, *, calculation_consumers=None):
    """Freeze context; policies are applied only with an explicit calculation binding.

    Existing review-only callers supply no consumers and consume neutral weights.
    A calculation which actually uses a policy must name its consumer here and
    use those exact parameters. Merely discovering a validated policy is not use.
    """
    calculation_consumers = calculation_consumers or {}
    version = reliability_version(public_store, now)
    inputs = []
    for cid in sorted(set(claim_ids)):
        found = public_store.feedback("claim", cid)
        if not found:
            raise ValueError("Public feedback claim unavailable")
        item = found[0]; assessment = current_assessment(public_store, item, as_of=now)
        if instant(item["firstAvailableAt"]) > instant(now):
            raise ValueError("Claim unavailable at comparison origin")
        inputs.append({"claim": {**item, "sourceQuality": next(iter(public_store.feedback("news-source-quality", item["id"])), None)}, "assessment": assessment})
    body = {"contractVersion": "shared-feedback-v1", "inputs": inputs, "reliabilityVersion": version,
            "appliedDependencies": [applied_dependency(public_store, row['claim'], now,
                calculation_consumers.get(row['claim']['id'])) for row in inputs],
            "effect": "Calculation consumer bindings preserve actually used parameters" if calculation_consumers else
                "Review context only; collecting corrections do not change calculated waiting, arrival, fuel or cost"}
    body["id"] = identifier(body)
    visitor_store.append_feedback("consumption", body)
    return body


def require_consumption(public_store, consumed, now=None):
    from src.portwatch_os.clock import wall_now
    now = now or wall_now().isoformat()
    for entry in consumed["inputs"]:
        latest = current_assessment(public_store, entry["claim"], as_of=now)
        if assessment_dependency(latest) != assessment_dependency(entry['assessment']):
            raise ValueError("Consumed verification changed; refresh a linked successor for fresh review")
        revisions = [c for c in public_store.feedback('claim') if c.get('supersedesClaimId') == entry['claim']['id']
                     and instant(c['firstAvailableAt']) <= instant(now)]
        if revisions:
            raise ValueError('Consumed claim revised; refresh a linked successor for fresh review')
    frozen = consumed.get('appliedDependencies')
    if frozen is None:
        # Old neutral collecting snapshots stay inspectable. Their global
        # descriptive counts were not applied calculation dependencies.
        frozen = [neutral_dependency(row['claim']) for row in consumed['inputs']]
    else:
        claims = {row['claim']['id']: row['claim'] for row in consumed['inputs']}
        # Earlier snapshots discovered matching policy rows without binding a
        # calculation consumer. Preserve their audit but do not call them used.
        frozen = [dependency if dependency.get('calculationConsumer') else
                  neutral_dependency(claims[dependency['claimId']]) for dependency in frozen]
    consumers = {dependency['claimId']: dependency.get('calculationConsumer') for dependency in frozen}
    latest = [applied_dependency(public_store, row['claim'], now, consumers.get(row['claim']['id']))
              for row in consumed['inputs']]
    if latest != frozen:
        raise ValueError('Consumed applied reliability/correction changed; refresh a linked successor for fresh review')


def assessment_dependency(assessment):
    return {k:assessment.get(k) for k in ('verdict','applicability','evidenceIds')} if assessment else None


def neutral_dependency(item):
    context = [item['entity'], item['geography'], item['source'], item.get('unit'),
               item.get('aggregation'), item['target']['kind']]
    return {'claimId':item['id'], 'contextKey':identifier(context), 'policyId':None,
            'weight':1, 'correction':None, 'policyParameters':{}}


def applied_dependency(store, item, now, calculation_consumer=None):
    neutral = neutral_dependency(item)
    if not calculation_consumer:
        return neutral
    neutral = {**neutral, 'calculationConsumer': calculation_consumer}
    records = [p for p in store.feedback('applied-policy') if p['contextKey'] == neutral['contextKey']
               and p.get('calculationConsumer') == calculation_consumer
               and p.get('status') == 'VALIDATED_APPLIED' and instant(p['firstAvailableAt']) <= instant(now)]
    if not records:
        return neutral
    newest = max(instant(p['firstAvailableAt']) for p in records)
    live = [p for p in records if instant(p['firstAvailableAt']) == newest]
    if len(live) != 1:
        raise ValueError('Applicable applied policy has conflicting versions; explicit resolution required')
    latest = live[0]
    return {**neutral, 'policyId':latest['id'], 'weight':latest['weight'],
            'correction':latest.get('correction'), 'policyParameters':latest.get('policyParameters',{})}


def operational_action_basis(basis, option):
    """Semantic action identity, stable across role copies and source refreshes.

    A notice response/version is a forecast input, not the executed action.
    Route, vessel characteristics, requested movement and original schedule
    reference do belong to the action; changing those must not reuse its log.
    """
    episode = basis['operationalEpisode']
    plan = (basis.get('restriction') or {}).get('plan') or {}
    derived = option.evaluation.derived
    return {'contractVersion': 'operational-action-v1',
        'namespace': episode['namespace'], 'episodeId': episode['id'],
        'vesselId': episode['vesselId'], 'destinationPort': basis['portCode'],
        'action': getattr(option, 'action', 'CONDITIONAL_OPTION'),
        'parameters': getattr(option, 'params', {}),
        'requestedArrivalAt': derived.get('arrivalAt'),
        'requestedPassageAt': derived.get('requestedPassageAt'),
        'referenceArrivalAt': basis.get('earliestVoyageArrival') or basis['plannedArrival'],
        'declaredPassage': {key: plan.get(key) for key in
            ('areaId', 'route', 'direction', 'characteristics', 'passageAt',
             'postPassageHours', 'alternativeAccess', 'openingRequired',
             'emergencyTransit', 'timezoneAssumption', 'sourceFamily')} if plan else None}


def operational_action_id(basis, option):
    return identifier(operational_action_basis(basis, option))


def operational_metric_basis(basis, option, metric):
    """Define the actual quantity; exclude the predicted endpoint/value.

    Lock waiting, destination approach waiting, access and all-fast are distinct.
    Schedule shift is measured against the frozen declared destination arrival.
    """
    plan = (basis.get('restriction') or {}).get('plan') or {}
    derived = option.evaluation.derived
    scope = plan.get('areaId') or basis['portCode']
    common = {'contractVersion': 'operational-metric-v1', 'metric': metric,
              'destinationPort': basis['portCode']}
    if metric == 'SCHEDULE_SHIFT':
        return {**common, 'measurement': 'ACTUAL_DESTINATION_ARRIVAL_MINUS_DECLARED_REFERENCE',
                'referenceArrivalAt': basis.get('earliestVoyageArrival') or basis['plannedArrival'],
                'arrivalMeaning': 'DESTINATION_APPROACH_ARRIVAL; not berth or all-fast'}
    if metric == 'WAITING':
        return {**common, 'scope': scope,
                'measurement': 'ACTUAL_ACCESS_MINUS_REQUESTED_ACCESS; lower bound zero',
                'requestedAccessAt': derived.get('requestedPassageAt') or derived.get('arrivalAt'),
                'waitingMeaning': 'SCHEDULED_ACCESS_WAIT; not measured anchorage or berth wait'}
    if metric == 'ACCESS_TIME':
        return {**common, 'scope': scope, 'measurement': 'ACTUAL_CONFIRMED_ACCESS_INSTANT',
                'accessMeaning': 'ACCESS_TO_DECLARED_ASSET; not destination berth or all-fast'}
    raise ValueError('Unsupported operational metric')


def record_operational_targets(store, problem):
    """Option hypotheses, never confused with source-report verification."""
    basis = problem.evidence.get("intelligenceBasis")
    if not basis or not basis.get('operationalEpisode'):
        return
    episode = basis['operationalEpisode']
    for option in problem.options:
        derived = option.evaluation.derived
        access = derived.get("earliestScheduledAccess")
        action_basis = operational_action_basis(basis, option)
        action_id = operational_action_id(basis, option)
        metrics = {"SCHEDULE_SHIFT": (option.evaluation.objectives["eta"].value, "hours"),
                   "WAITING": (option.evaluation.objectives["port_wait"].value, "hours"),
                   "ACCESS_TIME": (instant(access).timestamp() if access else None, "UTC epoch seconds")}
        for name, (value, unit) in metrics.items():
            if not finite(value):
                continue
            metric_basis = operational_metric_basis(basis, option, name)
            target_at=(derived.get('earliestDestinationArrival') or derived.get('arrivalAt') or basis['plannedArrival']) if name=='SCHEDULE_SHIFT' else (access or derived.get('arrivalAt') or basis['plannedArrival'])
            item = claim(store, {"kind": "FORECAST", "wording": "Conditional option " + name + "; suitable actual records required",
                "value": value, "unit": unit, "aggregation": "SELECTED_VOYAGE_OPTION",
                "entity": problem.subject_id, "geography": basis["portCode"], "originAt": basis['availableAt'],
                "target": {"kind": name, "at": target_at,
                           "decisionId": problem.decision_id, "optionId": option.option_id},
                "operationalEpisode":episode, "operationalActionId":action_id,
                "actionBasis":action_basis, "actionBasisSha256":identifier(action_basis),
                "metricBasis":metric_basis, "metricBasisSha256":identifier(metric_basis),
                "predictionVintageId":identifier([episode['namespace'],episode['id'],basis['evidenceId'],action_id,name]),
                "representation":'PORT_REVIEW' if problem.evidence.get('companyProposal') else 'COMPANY_SOURCE',
                "independentTargetKey": identifier([episode['namespace'],episode['id'],name]),
                "firstAvailableAt": basis['availableAt'], "source": "PortWatch conditional scenario",
                "sourceVersion": basis["evidenceId"], "eventKey": problem.decision_id + ":" + name,
                "independenceKey": "PortWatch scenario", "inputs": [{"firstAvailableAt": basis["availableAt"], "evidenceId": basis["evidenceId"]}], "operatorAssumptions": basis["assumptions"],
                "consumedEvidence": basis, "scoreEligibility": "Only selected action with independent actual operational records"})
            register_prediction(store, item, "operational_consequence")


def select_operational_targets(store, problem):
    if problem.workflow != "APPROVED" or not problem.human_choice:
        return
    approval = next((h for h in getattr(problem, 'workflow_history', [])
                     if h['state'] == 'APPROVED' and h.get('at')), None)
    if not approval:
        # Creation is not an approval timestamp; do not invent a cutoff basis.
        return
    for item in store.feedback("claim"):
        if item["target"].get("decisionId") == problem.decision_id and item["target"].get("optionId") == problem.human_choice:
            if store.feedback('selected-impact', item['id']):
                continue
            store.append_feedback("selected-impact", {"id": item["id"], "decisionId": problem.decision_id,
                "optionId": problem.human_choice, "selectionKind": "APPROVED_CONDITIONAL_PLAN",
                "selectedAt":approval['at'],
                "operationalActionId":item.get('operationalActionId')})
