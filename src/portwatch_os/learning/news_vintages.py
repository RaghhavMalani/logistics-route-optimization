"""Deterministic, as-of news identities and descriptive source agreement.

Event/target identities never contain reported values. Source documents and
their revisions are separate identities; a syndicated document is another
representation of its declared lineage, not another independent target.
"""
from datetime import date, datetime, timezone
import hashlib
import json
import re

POLICY = 'EXPLICIT_SUPERSESSION_AS_OF_V1'
NEWS_KINDS = {'ANNOUNCEMENT', 'ACTUAL_EVENT', 'CANCELLATION'}


def _hash(kind, value):
    return hashlib.sha256(json.dumps([kind, value], sort_keys=True, allow_nan=False).encode()).hexdigest()


def _instant(value):
    moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if not moment.tzinfo:
        raise ValueError('Explicit timezone required')
    return moment.astimezone(timezone.utc)


def _bound(value):
    if not isinstance(value, str):
        raise ValueError('Explicit period bound required')
    if len(value) == 10:
        return date.fromisoformat(value).isoformat(), 'DATE_ONLY'
    return _instant(value).isoformat(), 'INSTANT'


def period(target):
    """Keep date precision; never infer a period from a number or publication."""
    explicit = target.get('reportedPeriod')
    if explicit is not None and not isinstance(explicit, dict):
        return {'status': 'AMBIGUOUS', 'reason': 'UNKNOWN_REPORTING_PERIOD', 'original': explicit}
    supplied = explicit if explicit is not None else target
    start = supplied.get('from', supplied.get('start'))
    end = supplied.get('through', supplied.get('end'))
    if start is None and end is None and supplied.get('date'):
        start = end = supplied['date']
    if start is None and end is None and supplied.get('at'):
        start = end = supplied['at']
    try:
        first, first_precision = _bound(start)
        last, last_precision = _bound(end)
        if first_precision != last_precision or last < first:
            raise ValueError('Incompatible period bounds')
        supplied_precision = supplied.get('precision')
        precision = first_precision
        if supplied_precision:
            precision = {'DATE': 'DATE_ONLY', 'DATE_ONLY': 'DATE_ONLY', 'DAY': 'DATE_ONLY',
                'INSTANT': 'INSTANT', 'TIMESTAMP': 'INSTANT', 'SECOND': 'INSTANT',
                'MINUTE': 'MINUTE'}.get(str(supplied_precision).upper())
            if not precision or (precision == 'DATE_ONLY') != (first_precision == 'DATE_ONLY'):
                raise ValueError('Unknown or incompatible reporting precision')
            if precision == 'MINUTE' and any(_instant(v).second or _instant(v).microsecond for v in (first, last)):
                raise ValueError('Period bounds exceed declared minute precision')
        return {'status': 'KNOWN', 'from': first, 'through': last, 'precision': precision,
                'declaredPrecision': supplied_precision}
    except (TypeError, ValueError):
        return {'status': 'AMBIGUOUS', 'reason': 'UNKNOWN_OR_INVALID_REPORTING_PERIOD',
                'original': {'from': start, 'through': end, 'precision': supplied.get('precision')}}


def lineage(record):
    return record.get('sourceLineageId') or record.get('independenceKey')


def identity(item):
    """Additive identity view; historical claim IDs and bodies are untouched."""
    target = item['target']
    reference = item.get('eventReference') or item.get('eventKey')
    legacy_nav = item.get('reviewedSourceFamily') == 'NAVCEN_MSI_53842' or (
        item.get('entity') == 'WRIGHTSVILLE_SR74' and
        re.fullmatch(r'USCG MSI #53842:\d{4}-\d{2}-\d{2}:WRIGHTSVILLE_SR74', str(item.get('eventKey'))))
    if legacy_nav and not item.get('eventReference'):
        reference = 'NAVCEN_MSI:53842:'+item['entity']
    # The retained headline adapter once included the count in eventKey. Its
    # explicit predicate identifies the family, but its unknown period still
    # prevents a known event/target from being asserted or scored.
    if not item.get('eventReference') and target.get('predicate') == 'CENTCOM_REPORTED_CUMULATIVE_REDIRECTIONS':
        reference = 'CENTCOM:HORMUZ:CUMULATIVE_REDIRECTIONS'
    family = {'reference': reference, 'entity': item.get('entity'), 'geography': item.get('geography')}
    normalized_target = target
    if legacy_nav and not target.get('precision') and not target.get('reportedPeriod'):
        try:
            bounds = [_instant(target[key]) for key in ('from', 'through')]
            if all(not at.second and not at.microsecond for at in bounds):
                normalized_target = {**target, 'precision': 'MINUTE'}
        except (KeyError, TypeError, ValueError):
            pass
    measured_period = period(normalized_target)
    source_lineage = lineage(item)
    report_reference = item.get('sourceReportId') or ('NAVCEN_MSI:53842'
        if item.get('reviewedSourceFamily') == 'NAVCEN_MSI_53842' else item.get('source'))
    source_revision = item.get('sourceRevisionId') or item.get('sourceVersion')
    reasons = []
    if not all(family.values()):
        reasons.append('MISSING_EVENT_REFERENCE_OR_SCOPE')
    if measured_period['status'] != 'KNOWN':
        reasons.append('AMBIGUOUS_PERIOD')
    if not source_lineage or not report_reference or not source_revision:
        reasons.append('MISSING_SOURCE_LINEAGE_REPORT_OR_REVISION')
    if not item.get('unit') or not item.get('aggregation'):
        reasons.append('MISSING_UNIT_OR_AGGREGATION')
    event_period = {key: measured_period.get(key) for key in ('from', 'through', 'precision')}
    event_id = _hash('event', [family, event_period]) if all(family.values()) and measured_period['status'] == 'KNOWN' else None
    ignored = {'from', 'through', 'start', 'end', 'date', 'at', 'reportedPeriod', 'precision', 'timePrecision', 'timeZoneBasis'}
    semantics = {k: v for k, v in target.items() if k not in ignored}
    target_id = _hash('target', [event_id, semantics, item.get('unit'), item.get('aggregation')]) if event_id and item.get('unit') and item.get('aggregation') else None
    lineage_id = _hash('lineage', source_lineage) if source_lineage else None
    report_id = _hash('report', [lineage_id, report_reference]) if report_reference and lineage_id else None
    revision_id = _hash('revision', [report_id, source_revision]) if report_id and source_revision else None
    return {'claimId': item.get('id'), 'eventFamilyId': _hash('event-family', family),
            'eventReference': reference, 'eventId': event_id, 'targetId': target_id,
            'lineageId': lineage_id, 'sourceLineage': source_lineage,
            'lineageBasis': 'EXPLICIT_DECLARED_LINEAGE' if item.get('sourceLineageId') else
                'LEGACY_DECLARED_INDEPENDENCE_KEY; not proof of independent reporting',
            'reportId': report_id, 'revisionId': revision_id, 'period': measured_period,
            'status': 'AMBIGUOUS' if reasons else 'IDENTIFIED', 'reasons': reasons}


def _parents(item):
    many = item.get('supersedesClaimIds', [])
    if not isinstance(many, list) or any(not isinstance(v, str) for v in many):
        raise ValueError('INVALID_SUPERSESSION_REFERENCE')
    one = item.get('supersedesClaimId')
    if one is not None and not isinstance(one, str):
        raise ValueError('INVALID_SUPERSESSION_REFERENCE')
    return sorted(set(many + ([one] if one else [])))


def _value(item):
    return json.dumps(item.get('value'), sort_keys=True, allow_nan=False)


def _counts(items, ids):
    report_ids = {ids[c['id']]['reportId'] for c in items if ids[c['id']]['reportId']}
    revision_ids = {ids[c['id']]['revisionId'] for c in items if ids[c['id']]['revisionId']}
    return {'reportCount': len(report_ids), 'revisionCount': len(revision_ids),
            'additionalRevisionCount': max(0, len(revision_ids)-len(report_ids)), 'claimCount': len(items)}


def aggregate(store, as_of, *, assessment_for=None):
    """Use only available nodes and explicit valid supersession edges.

    No timestamp or database order silently chooses among independent heads.
    Several agreeing syndicated heads represent one lineage/target. Conflicting
    values, invalid links, cycles and incompatible verification remain excluded.
    """
    available = [c for c in store.feedback('claim') if c.get('kind') == 'REPORTED_FACT'
                 and c.get('target', {}).get('kind') in NEWS_KINDS
                 and _instant(c['firstAvailableAt']) <= _instant(as_of)]
    available.sort(key=lambda c: c['id'])
    items = {c['id']: c for c in available}
    ids = {cid: identity(c) for cid, c in items.items()}
    reasons = {cid: set(ids[cid]['reasons']) for cid in items}
    edges = {cid: [] for cid in items}
    for cid, item in items.items():
        try:
            parents = _parents(item)
        except ValueError as exc:
            reasons[cid].add(str(exc)); continue
        for parent_id in parents:
            parent = items.get(parent_id)
            if parent is None:
                reasons[cid].add('SUPERSEDED_CLAIM_UNAVAILABLE_AS_OF'); continue
            parent_identity = ids[parent_id]
            if not ids[cid]['targetId'] or ids[cid]['targetId'] != parent_identity['targetId']:
                reasons[cid].add('CROSS_TARGET_SUPERSESSION'); continue
            if ids[cid]['lineageId'] != parent_identity['lineageId']:
                reasons[cid].add('CROSS_LINEAGE_SUPERSESSION'); continue
            edges[cid].append(parent_id)
            if _instant(parent['firstAvailableAt']) > _instant(item['firstAvailableAt']):
                reasons[cid].add('SUPERSESSION_PRECEDES_ORIGINAL_AVAILABILITY')
        previous_revision = item.get('sourcePreviousRevisionId')
        if previous_revision is not None:
            if not isinstance(previous_revision, str):
                reasons[cid].add('INVALID_SOURCE_REVISION_REFERENCE')
            else:
                # This is explicit source-version lineage, not a guess from
                # receipt order. Its older original may be imported later.
                # Only nodes available at the requested as-of participate.
                for parent_id, parent in items.items():
                    if previous_revision != (parent.get('sourceRevisionId') or parent.get('sourceVersion')):
                        continue
                    if (ids[parent_id]['reportId'] == ids[cid]['reportId']
                            and ids[parent_id]['lineageId'] == ids[cid]['lineageId']
                            and ids[cid]['targetId'] and ids[parent_id]['targetId'] == ids[cid]['targetId']):
                        edges[cid].append(parent_id)
        edges[cid] = sorted(set(edges[cid]))
    # Detect cycles independently of insertion order or invalid availability.
    def visit(cid, trail):
        if cid in trail:
            for node in trail[trail.index(cid):]: reasons[node].add('SUPERSESSION_CYCLE')
            return
        for parent in edges[cid]: visit(parent, trail+[cid])
    for cid in items: visit(cid, [])
    groups = {}
    for cid, item in items.items():
        key = (ids[cid]['targetId'] or 'ambiguous:'+ids[cid]['eventFamilyId'], ids[cid]['lineageId'])
        groups.setdefault(key, []).append(item)
    targets = []; exclusions = []; selected = {}
    for key, rows in sorted(groups.items(), key=lambda pair: str(pair[0])):
        group_ids = {r['id'] for r in rows}
        superseded = {parent for child in group_ids if not reasons[child] for parent in edges[child]}
        heads = [r for r in rows if r['id'] not in superseded]
        why = {reason for r in heads for reason in reasons[r['id']]}
        # A malformed ancestor cannot be laundered through a later correction.
        def ancestor_reasons(cid, seen=None):
            seen = set() if seen is None else seen
            if cid in seen: return set()
            seen.add(cid)
            return reasons[cid] | set().union(*(ancestor_reasons(p, seen) for p in edges[cid]))
        for head in heads: why.update(ancestor_reasons(head['id']))
        by_revision = {}
        for row in heads:
            by_revision.setdefault(ids[row['id']]['revisionId'], set()).add(_value(row))
        if any(len(values) > 1 for values in by_revision.values()):
            why.add('SAME_SOURCE_REVISION_CONFLICT')
        values = {_value(row) for row in heads}
        if len(values) > 1: why.add('UNRESOLVED_SAME_TARGET_VALUE_CONFLICT')
        assessments = [assessment_for(row) if assessment_for else _assessment(store, row, as_of) for row in heads]
        verdicts = {a['verdict'] if a else 'UNRESOLVED' for a in assessments}
        applicability = {a.get('applicability', 'AS_REPORTED') if a else 'AS_REPORTED' for a in assessments}
        if len(verdicts) > 1: why.add('CONFLICTING_HEAD_VERIFICATION')
        if len(applicability) > 1: why.add('CONFLICTING_HEAD_APPLICABILITY')
        item = rows[0]; ident = ids[item['id']]
        target = {'eventId': ident['eventId'], 'targetId': ident['targetId'],
            'eventFamilyId': ident['eventFamilyId'],
            'lineageId': ident['lineageId'], 'sourceLineage': ident['sourceLineage'],
            'entity': item['entity'], 'geography': item['geography'], 'kind': item['target']['kind'],
            'period': ident['period'], 'status': 'EXCLUDED' if why else 'ELIGIBLE',
            'verdict': next(iter(verdicts)) if len(verdicts) == 1 and not why else 'UNRESOLVED',
            'applicability': next(iter(applicability)) if len(applicability) == 1 else 'AMBIGUOUS',
            'activeClaimIds': sorted(h['id'] for h in heads), 'supersededClaimIds': sorted(superseded),
            'reportIds': sorted({ids[r['id']]['reportId'] for r in rows if ids[r['id']]['reportId']}),
            'revisionIds': sorted({ids[r['id']]['revisionId'] for r in rows if ids[r['id']]['revisionId']}),
            'exclusionReasons': sorted(why), **_counts(rows, ids)}
        targets.append(target)
        if why:
            exclusions.append({'claimIds': sorted(group_ids), 'targetId': ident['targetId'],
                'lineageId': ident['lineageId'], 'reason': '; '.join(sorted(why))})
        for row in rows:
            selected[row['id']] = {**ids[row['id']], 'status': 'EXCLUDED' if why else
                'SUPERSEDED' if row['id'] in superseded else 'ACTIVE', 'reasons': sorted(why)}
    known = {t['targetId'] for t in targets if t['targetId']}
    eligible = {t['targetId'] for t in targets if t['status'] == 'ELIGIBLE'}
    resolved = {t['targetId'] for t in targets if t['status'] == 'ELIGIBLE'
                and t['verdict'] in ('CORROBORATED', 'CONTRADICTED')}
    return {'contractVersion': 'news-vintages-v1', 'policy': POLICY, 'asOf': _instant(as_of).isoformat(),
        'summary': {'eventCount': len({t['eventId'] for t in targets if t['eventId']}),
            'independentTargets': len(known), 'eligibleIndependentTargets': len(eligible),
            'resolvedIndependentTargets': len(resolved), 'pendingIndependentTargets': len(eligible-resolved),
            'ambiguousClaimCount': sum(ids[cid]['status'] == 'AMBIGUOUS' for cid in ids),
            'excludedTargetCount': sum(t['status'] == 'EXCLUDED' for t in targets), **_counts(available, ids)},
        'targets': targets, 'claims': [selected[cid] for cid in sorted(selected)], 'exclusions': exclusions}


def _assessment(store, item, as_of):
    rows = [a for a in store.feedback('assessment') if a['claimId'] == item['id']
            and _instant(a['assessedAt']) <= _instant(as_of)]
    return max(rows, key=lambda a: (_instant(a['assessedAt']), a.get('sequence', 0), a['id'])) if rows else None


def slices(aggregation):
    contexts = {}
    for target in aggregation['targets']:
        key = (target['sourceLineage'], target['entity'], target['kind'])
        contexts.setdefault(key, []).append(target)
    result = []
    for context, rows in sorted(contexts.items(), key=lambda pair: str(pair[0])):
        eligible = [r for r in rows if r['status'] == 'ELIGIBLE']
        resolved = [r for r in eligible if r['verdict'] in ('CORROBORATED', 'CONTRADICTED')]
        result.append({'context': list(context), 'independentTargets': len(resolved),
            'pendingTargets': len(eligible)-len(resolved), 'excludedTargets': len(rows)-len(eligible),
            'reportCount': len({value for row in rows for value in row['reportIds']}),
            'revisionCount': len({value for row in rows for value in row['revisionIds']}),
            'corroborated': sum(r['verdict'] == 'CORROBORATED' for r in resolved),
            'contradicted': sum(r['verdict'] == 'CONTRADICTED' for r in resolved),
            'exclusionReasons': sorted({why for row in rows for why in row['exclusionReasons']}),
            'status': 'COLLECTING', 'policy': POLICY,
            'meaning': 'Descriptive independent-target agreement; no source weight or operational-delay calibration'})
    return result


def dependency(aggregation, item):
    """Continuation depends on relevant conflicts, not descriptive counts/copies.

    Explicit revisions are also checked by the existing retained-claim guard.
    Unknown periods cannot establish that a later report is the same target.
    """
    ident = identity(item)
    if not ident['targetId'] or item.get('kind') != 'REPORTED_FACT':
        return None
    row = next((target for target in aggregation['targets']
                if target['targetId'] == ident['targetId'] and target['lineageId'] == ident['lineageId']), None)
    if row is None:
        return None
    return {key: row[key] for key in ('targetId', 'lineageId', 'status', 'verdict', 'applicability', 'exclusionReasons')}


def relevant_supersession(child, parent):
    """An invalid cross-target/lineage link cannot invalidate another approval."""
    try:
        explicit = parent['id'] in _parents(child)
    except ValueError:
        return False
    old, new = identity(parent), identity(child)
    by_version = (child.get('sourcePreviousRevisionId') is not None
        and child['sourcePreviousRevisionId'] == (parent.get('sourceRevisionId') or parent.get('sourceVersion'))
        and old['reportId'] == new['reportId'])
    if not explicit and not by_version:
        return False
    if not old['lineageId'] or old['lineageId'] != new['lineageId']:
        return False
    if old['targetId']:
        return old['targetId'] == new['targetId']
    return (old['eventFamilyId'] == new['eventFamilyId'] and parent['target'] == child['target']
            and parent.get('unit') == child.get('unit') and parent.get('aggregation') == child.get('aggregation'))
