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
from src.portwatch_os.learning import news_vintages
from src.portwatch_os.learning import economic_feedback

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


def target_eligibility(item):
    """Internal ledger due boundary; never a measurement or publication clock."""
    target = item['target']
    if target.get('kind') == 'ECONOMIC_OBSERVATION' and target.get('date'):
        from datetime import date
        day = date.fromisoformat(target['date'])
        return day.isoformat()+'T23:59:59+00:00'
    return target['at']


def claim(store, body):
    required = ("kind", "wording", "entity", "geography", "originAt", "target", "firstAvailableAt",
                "source", "sourceVersion", "inputs", "eventKey", "independenceKey")
    if any(key not in body for key in required) or body["kind"] not in CLAIM_KINDS:
        raise ValueError("Explicit claim semantics required")
    instant(body["originAt"]); instant(body["firstAvailableAt"])
    if body["kind"] == "FORECAST":
        economic = body['target'].get('kind') == 'ECONOMIC_OBSERVATION' and body['target'].get('date')
        if (economic and datetime.fromisoformat(body['target']['date']).date() <= instant(body['originAt']).date()) or (
                not economic and instant(body["target"]["at"]) <= instant(body["originAt"])):
            raise ValueError("A forecast must be frozen before its future target")
        if any(instant(i["firstAvailableAt"]) > instant(body["originAt"]) for i in body["inputs"]):
            raise ValueError("Consumed input was unavailable at forecast origin")
    value = {**body, "id": identifier(body), "contractVersion": "shared-feedback-v1"}
    store.append_feedback("claim", value)
    return value


def news_report(store, *, wording, source, source_version, independence_key, event_key,
                entity, geography, target, first_available_at, published_at, response_sha256, value=True, unit="boolean",
                event_reference=None, source_lineage_id=None, source_report_id=None, source_revision_id=None,
                supersedes_claim_id=None, supersedes_claim_ids=None):
    """Explicit reviewed event identity joins syndicated reports, not their truth.

    Callers must supply an event/reference key and exact extracted wording.
    Headline similarity alone is deliberately not an event identity.
    """
    if target.get("kind") not in news_vintages.NEWS_KINDS or not event_key or not wording:
        raise ValueError("A specific reviewed news target and event reference are required")
    if not response_sha256 or len(response_sha256) != 64:
        raise ValueError("Retained original news response required")
    return claim(store, {"kind": "REPORTED_FACT", "wording": wording, "value": value,
        "entity": entity, "geography": geography, "originAt": first_available_at,
        "target": target, "firstAvailableAt": first_available_at, "publishedAt": published_at,
        "source": source, "sourceVersion": source_version, "responseSha256": response_sha256,
        "eventKey": event_key, "independenceKey": independence_key, "inputs": [],
        "unit": unit, "aggregation": "EXPLICIT_NEWS_TARGET",
        **{key:value for key,value in {'eventReference':event_reference, 'sourceLineageId':source_lineage_id,
            'sourceReportId':source_report_id, 'sourceRevisionId':source_revision_id,
            'supersedesClaimId':supersedes_claim_id, 'supersedesClaimIds':supersedes_claim_ids}.items()
           if value is not None}})


def evidence(store, body):
    for key in ("eventKey", "target", "entity", "geography", "source", "sourceVersion", "independenceKey",
                "firstAvailableAt", "observedAt", "unit", "aggregation", "value", "recordKind", "responseSha256"):
        if key not in body:
            raise ValueError("Outcome identity, source and availability required: " + key)
    if not body["responseSha256"] or len(body["responseSha256"]) != 64:
        raise ValueError("Retained source response required")
    if body["recordKind"] == "ACTUAL_OPERATIONAL_RECORD" and not body.get("independentTargetKey"):
        raise ValueError("Actual operational records require an independent voyage/operation target identity")
    available = instant(body["firstAvailableAt"])
    date_only = body['recordKind'] == 'ECONOMIC_OBSERVATION' and body.get('observedAt') is None
    if date_only:
        day = economic_feedback.observation_date(body)
        if not day or available.date().isoformat() < day:
            raise ValueError('Observation date cannot follow first availability')
    else:
        instant(body["observedAt"])
    if not date_only and available < instant(body["observedAt"]):
        raise ValueError("Outcome cannot be available before observation")
    value = {**body, "id": identifier(body)}
    return store.append_feedback("evidence", value)


def retained_original_status(store, record):
    """Public original qualification, with no paths exposed in the response."""
    reader = getattr(store, "retained_original_status", None)
    if callable(reader):
        return reader(record)
    from pathlib import Path
    digest = record.get('responseSha256')
    if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
        return 'MISSING_ORIGINAL'
    from src.portwatch_os.intelligence import current_environment, operational_notices, navigation_restrictions
    roots = [current_environment.ROOT, operational_notices.ROOT, navigation_restrictions.ROOT]
    paths = [Path(root)/folder/(digest+'.response') for root in roots for folder in ('shared_feedback','operational_notices')]
    if getattr(store,'path',None) and str(store.path)!=':memory:':
        paths.extend(Path(store.path).parent/folder/(digest+'.response') for folder in ('shared_feedback','operational_notices'))
    for receipt in store.feedback('receipt'):
        if receipt.get('responseSha256')==digest and receipt.get('archivePath'):
            path=Path(receipt['archivePath'])
            if path.name==digest+'.response' and path.parent.name in ('shared_feedback','operational_notices'):
                paths.append(path)
    found=False
    for path in dict.fromkeys(paths):
        try:
            if path.is_file():
                found=True
                if hashlib.sha256(path.read_bytes()).hexdigest()==digest:
                    return None
        except OSError:
            pass
    return 'CORRUPT_ORIGINAL' if found else 'MISSING_ORIGINAL'


def _news_evidence_heads(rows):
    """Explicit same-target/lineage revisions; clocks never choose a truth."""
    by_id={row['id']:row for row in rows}; parents={}; reasons=[]
    for row in rows:
        parent=row.get('supersedes')
        if parent is None:
            parents[row['id']]=[];continue
        if not isinstance(parent,str) or parent not in by_id:
            reasons.append('SUPERSESSION_PARENT_UNAVAILABLE_OR_INCOMPATIBLE');parents[row['id']]=[];continue
        previous=by_id[parent]
        if news_vintages.lineage(row)!=news_vintages.lineage(previous) or instant(previous['firstAvailableAt'])>instant(row['firstAvailableAt']):
            reasons.append('INVALID_EVIDENCE_SUPERSESSION');parents[row['id']]=[];continue
        parents[row['id']]=[parent]
    def visit(node,path):
        if node in path:return True
        return any(visit(parent,path|{node}) for parent in parents.get(node,[]))
    if any(visit(node,set()) for node in parents):reasons.append('CYCLIC_EVIDENCE_SUPERSESSION')
    if reasons:return [],sorted(set(reasons))
    superseded={parent for values in parents.values() for parent in values}
    return [row for row in rows if row['id'] not in superseded],[]


def news_assessment(store, report, now):
    """Exact, original-backed source assessment; never an occurrence forecast."""
    identity=news_vintages.identity(report)
    exclusions=[];matching=[];cancelled=[];primary_ids=set()
    original_problem=retained_original_status(store,report)
    if original_problem:exclusions.append(original_problem)
    if not identity['targetId']:exclusions.append('AMBIGUOUS_REPORTING_PERIOD')
    if not report.get('target',{}).get('predicate'):exclusions.append('UNQUALIFIED_LEGACY_PREDICATE')
    report_visible=instant(report['firstAvailableAt'])<=instant(now)
    if not report_visible:exclusions.append('REPORT_UNAVAILABLE_AS_OF')
    for row in store.feedback('evidence'):
        try:
            if instant(row['firstAvailableAt'])>instant(now):continue
            ri=news_vintages.identity(row)
            if ri['eventFamilyId']!=identity['eventFamilyId']:continue
            if row['entity']!=report['entity'] or row['geography']!=report['geography']:
                continue
            if not identity['targetId'] or ri['targetId']!=identity['targetId']:
                exclusions.append('INCOMPATIBLE_TARGET_OR_PERIOD');continue
            if row['unit']!=report.get('unit') or row['aggregation']!=report.get('aggregation'):
                exclusions.append('INCOMPATIBLE_UNIT_OR_STATISTIC');continue
            raw_problem=retained_original_status(store,row)
            if raw_problem:exclusions.append(raw_problem);continue
            if row['recordKind']=='CANCELLATION':
                if row.get('cancelsSourceVersion')==report['sourceVersion']:
                    cancelled.append(row)
                continue
            if row['recordKind'] not in ('AUTHORITY_RECORD','OPERATOR_RECORD'):
                exclusions.append('UNSUPPORTED_EVIDENCE_PREDICATE');continue
            primary_check=getattr(news_vintages,'primary_announcement_verification',lambda *_:False)
            primary=primary_check(report,row)
            self_reference=(news_vintages.lineage(row)==news_vintages.lineage(report) or
                row.get('derivedFrom') in (report['independenceKey'],news_vintages.lineage(report)) or
                row.get('responseSha256')==report.get('responseSha256') or row.get('sourceReportId')==report.get('sourceReportId') and row.get('sourceReportId') is not None)
            if self_reference and not primary:
                exclusions.append('SELF_REFERENCE_OR_SYNDICATED_ORIGIN');continue
            if primary:primary_ids.add(row['id'])
            matching.append(row)
        except (ValueError,TypeError,KeyError):
            exclusions.append('MALFORMED_OR_UNSUPPORTED_EVIDENCE')
    live, revision_problems=_news_evidence_heads(matching)
    exclusions.extend(revision_problems)
    verdicts={'CORROBORATED' if row['value']==report.get('value') else 'CONTRADICTED' for row in live}
    verdict=next(iter(verdicts)) if len(verdicts)==1 and report_visible and not original_problem and identity['targetId'] and report['target'].get('predicate') else 'UNRESOLVED'
    if len(verdicts)>1:exclusions.append('CONFLICTING_EVIDENCE')
    if original_problem or not identity['targetId'] or not report_visible:
        live=[];cancelled=[]
    primary_live=[row for row in live if row['id'] in primary_ids]
    reason=('Report unavailable at the requested as-of time' if not report_visible else
        'Reporting period ambiguous; matching cannot be established' if not identity['targetId'] else
        'Retained original is missing or corrupt; prior assessments remain inspectable' if original_problem else
        'Exact legacy predicate is unqualified; a newly available versioned interpretation is required' if not report['target'].get('predicate') else
        'Conflicting or invalid evidence revisions remain unresolved' if len(verdicts)>1 or revision_problems else
        'Primary document corroborates the attributed announcement; shared authority origin is not independent reporting or proof of occurrence' if primary_live else
        'Independent evidence addresses the same target' if live else
        'Independent authority/operator evidence unavailable; absence is not contradiction')
    return {'claimId':report['id'],'eventKey':report['eventKey'],'verdict':verdict,
        'applicability':'SUPERSEDED' if cancelled else 'AS_REPORTED',
        'evidenceIds':sorted(row['id'] for row in live+cancelled),'reason':reason,
        'exclusionReasons':sorted(set(exclusions)),
        'verificationMode':'PRIMARY_DOCUMENT_ATTESTS_ATTRIBUTED_ANNOUNCEMENT' if primary_live else 'INDEPENDENT_EXACT_TARGET_EVIDENCE',
        'independentReportingConfirmations':len({news_vintages.lineage(row) for row in live if row['id'] not in primary_ids}),
        'occurrenceStatus':'NOT_ESTABLISHED_BY_ANNOUNCEMENT_ASSESSMENT' if report['target']['kind']=='ANNOUNCEMENT' else 'SEPARATE_EXACT_TARGET',
        'operationalEffectStatus':'NOT_OBSERVED','realOperationalTargetsAdded':0}


def verify_news(store, report, now):
    body = news_assessment(store, report, now)
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
    """Freeze persistence before a future calendar target; retain legacy records."""
    from datetime import date
    origin = instant(now)
    target = date.fromisoformat(target_date) if target_date else (origin+timedelta(days=1)).date()
    while target.weekday() >= 5:
        target += timedelta(days=1)
    if target <= origin.date():
        raise ValueError('A forecast must be frozen before its future target date')
    if quote['unit'] != FX_UNIT or quote['aggregation'] != FX_AGGREGATION or not finite(quote['value']) or quote['value'] <= 0:
        raise ValueError('A finite DEXINUS noon rate in INR per USD is required')
    if instant(quote['firstAvailableAt']) > origin:
        raise ValueError('Consumed input was unavailable at forecast origin')
    day = economic_feedback.observation_date(quote)
    if not day or date.fromisoformat(day) > origin.date():
        raise ValueError('Input quote observation date follows forecast origin')
    problem, reason = economic_feedback._raw_status(store, quote)
    if problem:
        raise ValueError(reason)
    date_text = target.isoformat()
    existing = [c for c in store.feedback('claim') if c['target'].get('series') == 'DEXINUS'
                and c['kind'] == 'FORECAST' and c['target'].get('date') == date_text]
    if existing:
        return min(existing,key=lambda c:(instant(c['originAt']),c['id']))
    age = (origin.date()-date.fromisoformat(day)).days
    item = claim(store, {'kind':'FORECAST', 'wording':'Persistence forecast: next target-date DEXINUS equals the latest retained quote',
        'value':quote['value'], 'unit':FX_UNIT, 'aggregation':FX_AGGREGATION,
        'entity':'USD/INR', 'geography':'India / New York reference rate', 'originAt':now,
        'target':{'kind':'ECONOMIC_OBSERVATION','series':'DEXINUS','date':date_text,'timePrecision':'DATE_ONLY'},
        'firstAvailableAt':now, 'source':'PortWatch persistence baseline', 'sourceVersion':'persistence-v1',
        'forecastPolicy':'persistence-v1','targetIdentityVersion':'economic-date-target-v2',
        'eventKey':'DEXINUS:'+date_text, 'independenceKey':'PortWatch persistence baseline','inputs':[quote],
        'productId':economic_feedback.PRODUCT,'baseCurrency':'USD','quoteCurrency':'INR',
        'releasePolicy':economic_feedback.METADATA['releaseRule'],
        'missingDatePolicy':'No interpolation or carry-forward as outcome', 'status':'COLLECTING',
        'baselineObservationDate':day, 'baselineAgeDays':age,
        'baselineStatus':'STALE' if age>7 else 'RECENT_OBSERVATION'})
    register_prediction(store,item,'economic_persistence')
    return item


def register_prediction(store, item, model):
    if store.get_prediction(item["id"]):
        return
    value = item["value"]
    store.record_prediction(PredictionRecord(prediction_id=item["id"], domain="event" if model == "economic_persistence" else "route",
        kind=CONTINUOUS, target=item["target"]["kind"], subject=item["entity"], model=model,
        model_version="shared-feedback-v1", issued_at=item["originAt"], valid_at=target_eligibility(item),
        context=PredictionContext(region=item["geography"], horizon_hours=(instant(target_eligibility(item))-instant(item["originAt"])).total_seconds()/3600),
        predicted_value=value, features={model: value, "__persistence__": value},
        provenance={"feedbackClaimId": item["id"], "unit": item["unit"], "aggregation": item["aggregation"]}))


def reconcile(store, now):
    """Existing Outcome Agent, scoped to this feedback family, with causal qualification."""
    claims={c['id']:c for c in store.feedback('claim') if c['kind']=='FORECAST' and instant(c['firstAvailableAt'])<=instant(now)}
    outcomes=store.feedback('evidence')
    selections={cid:economic_feedback.select_outcome(store,item,now) for cid,item in claims.items()
                if item['target']['kind']=='ECONOMIC_OBSERVATION'}
    def observe(row):
        item=claims[row.prediction_id]
        if item['target']['kind']=='ECONOMIC_OBSERVATION':
            selection=selections[item['id']]
            if not selection['eligible']:return None
            first=selection['evidence']
            old=store.feedback('match',item['id'])
            if old and old[0]['evidenceId']!=first['id']:return None
            if not old:
                store.append_feedback('match',{'id':item['id'],'claimId':item['id'],'evidenceId':first['id'],
                    'availableAt':first['firstAvailableAt'],'assessedAt':now,
                    'selectionPolicy':economic_feedback.SELECTION_POLICY,'scoringVintage':'FIRST_RETAINED_OUTCOME'})
            return first['value'],now,first['source']
        selected=store.feedback('selected-impact',item['id'])
        if not selected or not item.get('operationalEpisode'):return None
        allowed=[e for e in outcomes if e['recordKind']=='ACTUAL_OPERATIONAL_RECORD'
                 and instant(item['originAt'])<instant(e['firstAvailableAt'])<=instant(now)
                 and instant(e['observedAt'])>instant(item['originAt']) and finite(e['value'])
                 and operational_record_matches(e,item) and execution_cutoff(e,item,selected[0])]
        if not allowed or len({instant(e['forecastCutoffAt']) for e in allowed})>1:return None
        first=min(allowed,key=lambda e:(instant(e['firstAvailableAt']),e['id']))
        store.append_feedback('match',{'id':item['id'],'claimId':item['id'],'evidenceId':first['id'],
            'availableAt':first['firstAvailableAt'],'scoringVintage':'FIRST_RETAINED_OUTCOME'})
        return first['value'],first['firstAvailableAt'],first['source']
    class ScopedPredictions:
        def predictions(self,status=None,**kwargs):
            return [row for cid in sorted(claims) if (row:=store.get_prediction(cid)) and (status is None or row.status==status)]
        def __getattr__(self,key):return getattr(store,key)
    result=OutcomeAgent(ScopedPredictions(),observer=observe).resolve_due(now=now)
    for cid,selection in selections.items():
        if not selection['eligible']:continue
        first=selection['evidence'];row=store.get_prediction(cid);match=store.feedback('match',cid)
        if not row or row.status!='resolved' or row.observed_value!=first['value'] or not match or match[0]['evidenceId']!=first['id']:
            continue
        key=identifier([economic_feedback.SELECTION_POLICY,cid,first['id']])
        if store.feedback('economic-qualification',key):continue
        store.append_feedback('economic-qualification',{'id':key,'claimId':cid,'evidenceId':first['id'],
            'assessedAt':now,'availableAt':now,'selectionPolicy':economic_feedback.SELECTION_POLICY,
            'scoringVintage':'FIRST_RETAINED_OUTCOME','predicted':claims[cid]['value'],'observed':first['value'],
            'error':first['value']-claims[cid]['value'],'absoluteError':abs(first['value']-claims[cid]['value']),
            'errorConvention':'observed minus predicted','legacyScorePreserved':not bool(match[0].get('assessedAt'))})
    return result


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


def reliability_version(store, now, *, persist=True):
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
        if not operational:
            continue
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
    economic = economic_feedback.inspect_economics(store,now)
    for part in economic['slices']:
        slices.append({**part,'context':['USD/INR','India / New York reference rate','economic_persistence',FX_UNIT,FX_AGGREGATION,'ECONOMIC_OBSERVATION',str(part['horizonCalendarDays'])+' calendar days'],
                       'consumedWeight':1,'fittedWeight':1,'status':'COLLECTING',
                       'reason':'Descriptive persistence errors; no independent improvement over the same baseline or applied correction'})
    aggregation = news_vintages.aggregate(store, now, assessment_for=lambda item: news_assessment(store, item, now))
    news_slices = news_vintages.slices(aggregation)
    body = {"contractVersion": "shared-feedback-v1", "status": "COLLECTING", "consumedWeight": 1,
            "correction": None, "minimumSamplesForReliability": MIN_SAMPLES_TO_APPLY,
            "slices": slices, "newsSlices": news_slices, "sampleIds": sorted([r.prediction_id for r in independent.values()]+economic.get("selectedClaimIds",[])),
            "errorConvention": "observed minus predicted", "scope": "Source accuracy and shipping impact scored separately"}
    body['operationalSelectionPolicy'] = 'LATEST_APPROVED_FORECAST_BEFORE_EXECUTED_LOG_CUTOFF_V1'
    body['excludedTargets'] = exclusions
    if not persist:
        return {**body,'id':identifier(body),'createdAt':now,'projection':'READ_ONLY_AS_OF'}
    old = store.feedback("version", identifier(body))
    if old:
        return old[0]
    return store.append_feedback("version", {**body, "id": identifier(body), "createdAt": now})


def inspect(store, now, *, kind='ALL', offset=0, limit=100, claim_id=None):
    """Read-only complete-dataset summaries with an explicitly separate visible page."""
    as_of=instant(now);now=as_of.isoformat()
    if kind not in ('ALL','ECONOMIC_FORECAST','NEWS'):raise ValueError('Unsupported feedback filter')
    if offset<0 or limit<1:raise ValueError('Invalid feedback page')
    economic=economic_feedback.inspect_economics(store,now)
    economics={row['claimId']:row for row in economic['targets']}
    items=[]
    for item in store.feedback('claim'):
        if instant(item['firstAvailableAt'])>as_of:continue
        row=store.get_prediction(item['id'])
        assessment=current_assessment(store,item,as_of=now)
        retained_match=next(iter(store.feedback('match',item['id'])),None)
        matching_id=retained_match.get('evidenceId') if retained_match else None
        outcomes=[e for e in store.feedback('evidence') if
            (e['eventKey']==item['eventKey'] and e['target']==item['target']) or e['id']==matching_id]
        def visible_outcome(e):
            if instant(e['firstAvailableAt'])>as_of:return False
            if e.get('observedAt') is not None:return instant(e['observedAt'])<=as_of
            return bool(e.get('recordKind')=='ECONOMIC_OBSERVATION' and economic_feedback.observation_date(e)<=as_of.date().isoformat())
        visible=[e for e in outcomes if visible_outcome(e)]
        match=(retained_match if retained_match and instant(retained_match.get('assessedAt') or retained_match['availableAt'])<=as_of
               and matching_id in {e['id'] for e in visible} else None)
        resolution_visible=bool(row and row.status=='resolved' and row.observed_at and instant(row.observed_at)<=as_of)
        entry={**item,'verification':assessment,'outcomes':visible,'match':match,
               'sourceQuality':next(iter(store.feedback('news-source-quality',item['id'])),None),
               'inspectionExclusions':[{'kind':'OUTCOME','reason':'Observation or receipt unavailable at the requested as-of time'} for e in outcomes if e not in visible]+
                   ([{'kind':'SCORE','reason':'Resolution unavailable at the requested as-of time'}] if row and row.status=='resolved' and not resolution_visible else []),
               'score':{'status':row.status if resolution_visible else 'open','observed':row.observed_value if resolution_visible else None,
                        'error':row.error if resolution_visible else None,'absoluteError':row.absolute_error if resolution_visible else None,
                        'availableAt':row.observed_at if resolution_visible else None} if row else None}
        if item['id'] in economics:
            detail=economics[item['id']];entry['economicInspection']=detail
            qualified=detail.get('assessmentAvailableAt') is not None and detail.get('error') is not None
            entry['score']={'status':'resolved' if qualified else 'open','observed':detail['matchedObservation']['value'] if qualified else None,
                            'error':detail['error'],'absoluteError':detail['absoluteError'],'availableAt':detail.get('assessmentAvailableAt')}
            if not qualified:entry['match']=None
        if item['target'].get('kind') in news_vintages.NEWS_KINDS:
            current=news_assessment(store,item,now)
            evidence_ids=set(current['evidenceIds'])
            entry['newsInspection']={'currentAssessment':{**current,'id':identifier(current)},'asOf':now,
                'evidence':[e for e in store.feedback('evidence') if e['id'] in evidence_ids and instant(e['firstAvailableAt'])<=as_of],
                'exclusionReasons':current['exclusionReasons'],
                'assessmentHistory':sorted([a for a in store.feedback('assessment') if a['claimId']==item['id'] and instant(a['assessedAt'])<=as_of],key=lambda a:(instant(a['assessedAt']),a['id']))}
        items.append(entry)
    aggregation=news_vintages.aggregate(store,now,assessment_for=lambda item:news_assessment(store,item,now))
    identities={row['claimId']:row for row in aggregation['claims']}
    for item in items:
        if item['id'] in identities:item['newsIdentity']=identities[item['id']]
    events=[]
    for event_id in sorted({r['eventId'] for r in identities.values() if r['eventId']}):
        reports=[item for item in items if identities.get(item['id'],{}).get('eventId')==event_id]
        events.append({'id':event_id,'reportIds':sorted(r['id'] for r in reports),
            'sourceIds':sorted({identities[r['id']]['lineageId'] for r in reports if identities[r['id']]['lineageId']}),
            'targets':[r['target'] for r in sorted(reports,key=lambda r:r['id'])]})
    filtered=[item for item in items if kind=='ALL' or kind=='ECONOMIC_FORECAST' and item['id'] in economics or
              kind=='NEWS' and item['target'].get('kind') in news_vintages.NEWS_KINDS]
    filtered.sort(key=lambda i:(instant(i['originAt']),i['id']),reverse=True)
    page=([item for item in filtered if item['id']==claim_id] if claim_id else filtered[offset:offset+limit])
    metrics=[{**part,'context':['DEXINUS','persistence-v1',str(part['horizonCalendarDays'])+' calendar days'],
              'targetFrom':part['targetDateFrom'],'targetThrough':part['targetDateThrough']} for part in economic['slices']]
    return {'contractVersion':'shared-feedback-v1','claims':page,'events':events,'newsAggregation':aggregation,
        'dataset':{'scope':'ALL_RETAINED_PUBLIC_CLAIMS_AS_OF','asOf':now,'totalClaims':len(items),'filteredClaims':len(filtered),
                   'offset':offset,'limit':limit,'returnedClaims':len(page),'hasMore':not claim_id and offset+len(page)<len(filtered),
                   'filter':kind,'selectedClaimId':claim_id},
        'economicSummary':{**economic['counts'],'metrics':metrics,'metadata':economic['metadata'],
                           'collector':economic['collector'],'selectionPolicy':economic['dataset']['selectionPolicy'],
                           'asOf':now,'errorConvention':'observed minus predicted','status':'COLLECTING'},
        'reliability':reliability_version(store,now,persist=False),'newsIndependentEvents':aggregation['summary']['eventCount'],
        'newsSourceReports':aggregation['summary']['reportCount'],'newsRevisionCount':aggregation['summary']['revisionCount'],
        'note':'Full as-of dataset summaries are independent of the displayed page. Source assessment, economic forecast error and real operational outcomes are separate. Simulation never verifies a real claim.'}


def freeze_consumption(public_store, visitor_store, claim_ids, now, *, calculation_consumers=None):
    """Freeze context; policies are applied only with an explicit calculation binding.

    Existing review-only callers supply no consumers and consume neutral weights.
    A calculation which actually uses a policy must name its consumer here and
    use those exact parameters. Merely discovering a validated policy is not use.
    """
    calculation_consumers = calculation_consumers or {}
    version = reliability_version(public_store, now)
    news_state = news_vintages.aggregate(public_store, now,
        assessment_for=lambda item: news_assessment(public_store, item, now))
    inputs = []
    for cid in sorted(set(claim_ids)):
        found = public_store.feedback("claim", cid)
        if not found:
            raise ValueError("Public feedback claim unavailable")
        item = found[0]; assessment = current_assessment(public_store, item, as_of=now)
        if instant(item["firstAvailableAt"]) > instant(now):
            raise ValueError("Claim unavailable at comparison origin")
        projected_news = item.get('target', {}).get('kind') in news_vintages.NEWS_KINDS
        if projected_news:
            # New consumption freezes the same current, evidence-qualified view
            # shown by inspection. The worker's older assessments remain audit
            # history, rather than making every new review stale until its next run.
            current = news_assessment(public_store, item, now)
            assessment = {**current, 'id': identifier(current), 'asOf': now,
                          'projection': 'READ_ONLY_AS_OF'}
        inputs.append({"claim": {**item, "sourceQuality": next(iter(public_store.feedback("news-source-quality", item["id"])), None)},
            "assessment": assessment, 'newsTargetDependency':news_vintages.dependency(news_state,item),
            **({'assessmentBasis':'CURRENT_AS_OF_PROJECTION_V1'} if projected_news else {})})
    body = {"contractVersion": "shared-feedback-v1", "inputs": inputs, "reliabilityVersion": version,
            "appliedDependencies": [applied_dependency(public_store, row['claim'], now,
                calculation_consumers.get(row['claim']['id'])) for row in inputs],
            "effect": "Calculation consumer bindings preserve actually used parameters" if calculation_consumers else
                "Review context only; collecting corrections do not change calculated waiting, arrival, fuel or cost"}
    body["id"] = identifier(body)
    visitor_store.append_feedback("consumption", body)
    return body


def require_consumption(public_store, consumed, now=None):
    from src.portwatch_os.clock import world_now
    now = world_now().isoformat() if now is None else now
    news_state = news_vintages.aggregate(public_store, now,
        assessment_for=lambda item: news_assessment(public_store, item, now))
    for entry in consumed["inputs"]:
        if entry.get('assessmentBasis') != 'CURRENT_AS_OF_PROJECTION_V1':
            latest = current_assessment(public_store, entry["claim"], as_of=now)
            if assessment_dependency(latest) != assessment_dependency(entry['assessment']):
                raise ValueError("Consumed verification changed; refresh a linked successor for fresh review")
        if entry['claim'].get('target',{}).get('kind') in news_vintages.NEWS_KINDS:
            current=news_assessment(public_store,entry['claim'],now)
            if assessment_dependency(current)!=assessment_dependency(entry['assessment']):
                raise ValueError('Consumed verification changed; refresh a linked successor for fresh review')
        if entry.get('newsTargetDependency') is not None and news_vintages.dependency(news_state,entry['claim']) != entry['newsTargetDependency']:
            raise ValueError('Consumed news target vintage/conflict changed; refresh a linked successor for fresh review')
        revisions = [c for c in public_store.feedback('claim') if news_vintages.relevant_supersession(c,entry['claim'])
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
    return {'verdict':(assessment or {}).get('verdict','UNRESOLVED'),
            'applicability':(assessment or {}).get('applicability','AS_REPORTED'),
            'evidenceIds':sorted((assessment or {}).get('evidenceIds') or [])}


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
        **({'declaredRemainingPassage': {
            **{key: basis['passagePlan'].get(key) for key in (
                'schemaVersion', 'referenceKind', 'referenceAt', 'referenceLabel',
                'remainingDistanceNm', 'distanceBasis', 'geometry', 'baselineArrivalAt',
                'departureHoldPermitted', 'departureHoldLocation')},
            'requestedApproachAt': basis['plannedArrival'],
        }} if basis.get('passagePlan') else {}),
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
