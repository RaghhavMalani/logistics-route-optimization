"""Rolling discovery plus bounded reviewed NAVCEN bridge-family extraction.

Discovery never establishes voyage exposure. Unreviewed prose, missing records
and failed requests cannot silently inherit a previous calculation's windows.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re
import threading
from zoneinfo import ZoneInfo
import requests
from src.portwatch_os.clock import wall_now
from src.portwatch_os.intelligence.current_environment import ROOT, instant
from src.portwatch_os.intelligence.source_registry import ASSETS, NAVCEN_SOURCE, registry

SOURCE = NAVCEN_SOURCE
CATALOGUE = 'https://www.navcen.uscg.gov/msi'
FEATURE_ID = 53842  # Compatibility default, never the discovery filter or asset identity.
AREA_ID = 'WRIGHTSVILLE_SR74'
EXTRACTION_VERSION = 'NAVCEN_MSI_BRIDGES_V2'
TTL = timedelta(hours=6)
LOCK = threading.RLock()


def _metadata(props, key):
    value = props.get(key)
    return datetime.fromtimestamp(value/1000, timezone.utc).isoformat() if isinstance(value, (int, float)) else None


def _json_safe(value):
    """Raw bytes are archived; non-finite source values cannot enter API JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


def _clock(value):
    value = value.strip().replace('a.m.', 'AM').replace('p.m.', 'PM')
    return datetime.strptime(value, '%I:%M %p' if ':' in value else '%I %p').time()


def _window(day, begin, end, asset):
    start = datetime.combine(day, _clock(begin), ZoneInfo(asset['timeZone']))
    finish = datetime.combine(day, _clock(end), ZoneInfo(asset['timeZone']))
    if finish <= start:
        raise ValueError('Unsupported crossing-midnight or reversed clock interval')
    return {'start': start.astimezone(timezone.utc).isoformat(), 'end': finish.astimezone(timezone.utc).isoformat(),
        'localStart': start.strftime('%H:%M'), 'localEnd': finish.strftime('%H:%M'), 'localDate': day.isoformat(),
        'timeZone': asset['timeZone'],
        'timeZoneBasis': 'OPERATOR_CONFIRMED_GEOGRAPHIC_ASSUMPTION; zone not stated in MSI body',
        'calculationSupported': True}


def _extract(text, asset):
    """Reviewed phrase grammars with exemptions; a headline cannot imply closure."""
    clock = r'(\d{1,2}(?::\d{2})? [ap]\.m\.)'
    template = asset['template']
    if template == 'SR74_CLOSED_POSITION_V2':
        match = re.search(r'S\.R\. 74 \(Wrightsville Beach\) Bridge will be maintained in the closed-to-navigation position from '
            + clock + r' to ' + clock + r' on (\w+ \d{1,2}, \d{4})', text)
        required = ('20 feet and 40 feet, respectively, above mean high water',
            'Vessels able to pass through the bridges in the closed-to-navigation position may do so at anytime.',
            'at least 15 minutes notice')
        if not match or not all(x in text for x in required):
            raise ValueError('Restriction, exemption or emergency semantics changed; adapter review required')
        dates = [datetime.strptime(match[3], '%B %d, %Y').date()]
        exceptions = 'Under-bridge transit permitted when able; emergency opening requires at least 15 minutes notice.'
    elif template == 'MARE_ISLAND_CLOSED_POSITION_V1':
        match = re.search(r'The lift span of the Bridge will be secured in the closed-to-navigation position from '
            + clock + r' to ' + clock + r' on (\w+ \d{1,2}, \d{4})', text)
        required = ('13 feet of vertical clearance at mean high water',
            'Vessels that can safely pass beneath the closed bridge may continue to transit at any time.')
        if not match or not all(x in text for x in required):
            raise ValueError('Restriction or closed-position exemption semantics changed; adapter review required')
        dates = [datetime.strptime(match[3], '%B %d, %Y').date()]
        exceptions = 'Under-bridge transit permitted when safe. Emergency-opening availability is not established.'
    elif template == 'PAMLICO_REPEATED_CLOSED_POSITION_V1':
        match = re.search(r'the bridge will be maintained in the closed-to-navigation position from '
            + clock + r' to ' + clock + r' on (\w+) ([\d\w ,]+), (\d{4})\.', text)
        required = ('Vessels able to pass through the bridge in the closed position may do so at any time.',
            'The bridge will not be able to open for emergencies.', 'The alternative dates are')
        if not match or not all(x in text for x in required):
            raise ValueError('Repeated restriction or exemption semantics changed; adapter review required')
        if not re.fullmatch(r'\d{1,2}(?:st|nd|rd|th)(?:, \d{1,2}(?:st|nd|rd|th))*(?:,? and \d{1,2}(?:st|nd|rd|th))', match[4]):
            raise ValueError('Unsupported day-list grammar; explicit review required')
        dates = [datetime.strptime(f'{match[3]} {day}, {match[5]}', '%B %d, %Y').date()
            for day in re.findall(r'\d{1,2}', match[4])]
        exceptions = 'Under-bridge transit permitted when able. Bridge cannot open for emergencies. Alternative dates are conditional and not activated by this adapter.'
    else:
        raise ValueError('No reviewed semantic extractor for asset')
    if re.search(r'\b(cancelled|canceled|withdrawn|superseded)\b', text, re.I):
        raise ValueError('Cancellation/revision prose needs explicit status review')
    # Variable clock/date tokens are extracted above. The rest of the reviewed
    # wording must still agree, including exceptions and any added qualification.
    # This prevents a surviving old phrase inside a changed notice from retaining
    # a calculation after unreviewed prose is appended or substituted.
    normalized = re.sub(r'\d{1,2}(?::\d{2})? [ap]\.m\.', '<CLOCK>', text)
    normalized = re.sub(r'\b\d{4}-\d{2}-\d{2}\b', '<ENVELOPE_DATE>', normalized)
    normalized = re.sub(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}', '<DATE>', normalized)
    normalized = re.sub(r'MSI #\d+', 'MSI #<ID>', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    if hashlib.sha256(normalized.encode()).hexdigest() != asset['reviewedTemplateSha256']:
        raise ValueError('Additional or changed prose outside reviewed variable fields; adapter semantics review required')
    return [_window(day, match[1], match[2], asset) for day in dates], exceptions


def _feature(feature):
    props = feature['properties']; text = props.get('DESCRIPTION', '')
    uid = str(props['MSI_UID']); geometry = feature.get('geometry') or {}
    coordinates = geometry.get('coordinates') if isinstance(geometry, dict) and geometry.get('type') == 'Point' else None
    lon, lat = coordinates[:2] if isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2 else (None, None)
    valid = (all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (lon, lat))
        and -180 <= lon <= 180 and -90 <= lat <= 90)
    if not valid: lon, lat = None, None
    named = [(key, a) for key, a in ASSETS.items() if re.search(a['namePattern'], text, re.I)]
    mapped = [(key, a) for key, a in named if lon is not None and lat is not None
        and abs(lon-a['lon']) <= .001 and abs(lat-a['lat']) <= .001]
    area_id, asset = mapped[0] if len(mapped) == 1 else (None, None)
    publisher_status = props.get('STATUS') if isinstance(props.get('STATUS'), str) else None
    cancelled = str(publisher_status).lower() in ('cancelled', 'canceled', 'withdrawn')
    facts = {'sourceFamily': 'NAVCEN_MSI', 'providerNoticeId': uid, 'noticeId': 'NAVCEN_MSI:'+uid,
        'noticeRef': 'USCG MSI #'+uid, 'areaId': area_id, 'assetId': area_id,
        'title': (asset['name']+' opening restriction') if asset else (props.get('TITLE')
            if isinstance(props.get('TITLE'), str) and props['TITLE'].strip() else 'Unreviewed bridge notice'),
        'area': props.get('WATERWAY_NAME') if isinstance(props.get('WATERWAY_NAME'), str) else None,
        'assetMappingStatus': 'REVIEWED' if asset else 'UNMAPPED',
        'coordinates': {'lon': lon, 'lat': lat, 'basis': 'Official MSI point; not a surveyed navigation chart or complete route'} if valid else None,
        'status': 'UNREVIEWED', 'publisherStatus': publisher_status, 'windows': [], 'originalWording': text,
        'issuer': 'U.S. Coast Guard / NAVCEN', 'providerCreatedAt': _metadata(props, 'CREATE_DATE'),
        'providerModifiedAt': _metadata(props, 'MODIFIED_DATE'), 'publishedAt': None,
        'publicationPrecision': 'PROVIDER_RECORD_METADATA; publication instant not established',
        'productFrom': _metadata(props, 'BEGIN_DATE'), 'productThrough': _metadata(props, 'END_DATE'),
        'providerWaterwayId': str(props.get('WTRW_UID', '')), 'providerMRN': props.get('MRN'),
        'sourceFeature': _json_safe(feature), 'extractionVersion': EXTRACTION_VERSION,
        'extractionStatus': 'UNSUPPORTED', 'calculationSupported': False, 'discoveryStatus': 'DISCOVERED',
        'restriction': 'Unreviewed notice; discovery does not establish a closure.',
        'applicability': {'vesselScope': 'NOT_ESTABLISHED'}, 'unaffectedAlternative': None,
        'confirmation': 'No actual opening, clearance or allocated slot is established by a source notice.',
        'mechanism': 'Review extraction and explicit voyage exposure before comparing an action.'}
    if cancelled:
        facts.update(status='CANCELLED', extractionStatus='SUPPORTED',
            reason='Explicit provider cancellation/withdrawal status; actual occurrence not inferred')
        return facts
    if not asset or props.get('SUB_CATEGORY') != 'Bridges':
        facts['reason'] = ('Reviewed bridge location changed; geographic review required' if named else
            'Asset or geometry not mapped to a reviewed calculation adapter')
        return facts
    facts['extractionStatus'] = 'SUPPORTED'
    if publisher_status != 'Approved':
        facts.update(extractionStatus='UNSUPPORTED', reason='Reviewed notice is not approved')
        return facts
    try:
        windows, exceptions = _extract(text, asset)
        if any((facts['productFrom'] and instant(w['start']) < instant(facts['productFrom']))
                or (facts['productThrough'] and instant(w['end']) > instant(facts['productThrough'])) for w in windows):
            raise ValueError('Explicit clock window falls outside provider validity envelope; review required')
    except ValueError as exc:
        facts.update(extractionStatus='UNSUPPORTED', reason=str(exc))
        return facts
    facts.update(status='SCHEDULED', windows=windows, calculationSupported=True, reason=None,
        semanticTemplate=asset['template'],
        restriction='Scheduled closed-to-navigation position; vessels able to pass beneath the closed bridge are excepted.',
        applicability={'vesselScope': 'DECLARED_PASSAGE_REQUIRING_BRIDGE_OPENING',
            'clearanceFeetMHW': asset['clearanceFeetMHW'],
            'characteristicRule': 'Declared opening requirement must account for actual water level and clearance; dimensions alone do not prove navigability.'},
        unaffectedAlternative=exceptions+' This comparison assumes ordinary, non-emergency passage.',
        confirmation='End of the published closed-position period is a conditional planning boundary, not confirmed opening, clearance or an allocated transit slot.',
        mechanism='Explicit declared passage at this bridge, requiring an opening, overlaps the published closed-position interval.')
    return facts


def discover(raw):
    product = json.loads(raw)
    if product.get('type') != 'FeatureCollection' or not isinstance(product.get('features'), list):
        raise ValueError('Expected NAVCEN bridge FeatureCollection')
    grouped = {}
    for feature in product['features']:
        if not isinstance(feature, dict) or not isinstance(feature.get('properties'), dict):
            continue  # Unidentified malformed entries remain in the complete raw archive.
        props = feature.get('properties') or {}
        if props.get('MSI_UID') is not None:
            grouped.setdefault(str(props['MSI_UID']), []).append(feature)
    notices = []
    for uid, entries in sorted(grouped.items()):
        try:
            facts = _feature(entries[0])
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            facts = {'sourceFamily': 'NAVCEN_MSI', 'providerNoticeId': uid, 'noticeId': 'NAVCEN_MSI:'+uid,
                'noticeRef': 'USCG MSI #'+uid, 'areaId': None, 'windows': [], 'status': 'UNREVIEWED',
                'title': 'Unreviewed bridge notice', 'coordinates': None, 'extractionVersion': EXTRACTION_VERSION,
                'extractionStatus': 'UNSUPPORTED', 'calculationSupported': False, 'sourceFeature': _json_safe(entries[0]), 'reason': str(exc)}
        if len(entries) != 1:
            facts.update(status='UNREVIEWED', extractionStatus='AMBIGUOUS', windows=[], calculationSupported=False,
                reason='Duplicate provider notice identity in one received product; neither row chosen as truth')
        notices.append(_json_safe(facts))
    return notices


def parse(raw, notice_id=None):
    """Strict single-notice compatibility entry point; rolling callers use discover."""
    uid = str(notice_id if notice_id is not None else FEATURE_ID).split(':')[-1]
    selected = [n for n in discover(raw) if n['providerNoticeId'] == uid]
    if len(selected) != 1:
        raise ValueError('Reviewed MSI feature absent or ambiguous; absence is not cancellation')
    facts = selected[0]
    if facts['extractionStatus'] != 'SUPPORTED':
        raise ValueError('Unreviewed restriction semantics: '+facts.get('reason', 'explicit review required'))
    return facts


def _lifecycle(notice, now):
    notice = dict(notice); windows = notice.get('windows') or []
    if notice.get('status') == 'SCHEDULED' and ((windows and all(instant(w['end']) <= now for w in windows))
            or (notice.get('productThrough') and instant(notice['productThrough']) <= now)):
        notice.update(status='EXPIRED', calculationSupported=False,
            lifecycleReason='Published restriction windows or product validity expired; actual occurrence remains unknown')
    return notice


def _write(path, value):
    temporary = path.with_suffix('.tmp'); temporary.write_text(json.dumps(value, indent=2)); temporary.replace(path)


def _hydrate_retained(root, previous, extracted_at, failure_reason):
    """Migrate a legacy single-notice pointer using its verified complete archive.

    This is a new historical extraction, never a successful provider receipt.
    Immutable legacy versions and response bytes are left untouched.
    """
    prior = {str(row.get('providerNoticeId', FEATURE_ID)): row for row in previous}
    archives = {}
    for row in previous:
        digest = row.get('responseSha256')
        if isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest):
            archives.setdefault(digest, row)
    for digest, retained in archives.items():
        original = root/(digest+'.response')
        if not original.is_file() or hashlib.sha256(original.read_bytes()).hexdigest() != digest:
            continue
        try:
            extracted = discover(original.read_bytes())
        except (ValueError, KeyError, TypeError):
            continue
        records = []
        first_source_receipt = retained.get('sourceFirstReceivedAt') or retained.get('availableAt')
        for facts in extracted:
            uid = facts['providerNoticeId']; before = prior.get(uid)
            semantics = {**facts, 'extractionMode': 'HISTORICAL_EXTRACTION_REPLAY',
                'historicalCalculationSupported': facts['calculationSupported'],
                'calculationSupported': False, 'sourceStatus': 'UNAVAILABLE'}
            revision = hashlib.sha256(json.dumps(semantics, sort_keys=True).encode()).hexdigest()
            path = root/(revision+'.json')
            if not path.exists():
                path.write_text(json.dumps({**semantics, 'revisionId': revision, 'semanticRevisionId': revision,
                    'id': revision, 'previousRevisionId': before.get('revisionId') if before else None,
                    'source': SOURCE, 'catalogueSource': CATALOGUE, 'responseSha256': digest,
                    'sourceFirstReceivedAt': first_source_receipt,
                    'sourceReceiptBasis': 'Existing legacy receipt of the complete hash-verified source product; not a new receipt',
                    'availableAt': extracted_at, 'extractedAt': extracted_at,
                    'availabilityBasis': 'First availability of this historical extraction under the rolling adapter; not provider freshness'}, indent=2))
            record = _lifecycle(json.loads(path.read_text()), instant(extracted_at))
            records.append({**record, 'historicalCalculationSupported': facts['calculationSupported'],
                'calculationSupported': False, 'sourceStatus': 'UNAVAILABLE', 'checkedAt': extracted_at,
                'reason': failure_reason+'; inspected from a retained original as historical extraction only'})
        return records
    # A missing/corrupt original cannot justify reconstructing a product. Keep
    # only a schema-compatible, blocked history reference rather than old windows.
    return [{**row, 'providerNoticeId': str(row.get('providerNoticeId', FEATURE_ID)),
        'noticeId': 'NAVCEN_MSI:'+str(row.get('providerNoticeId', FEATURE_ID)),
        'noticeRef': row.get('noticeRef') or 'USCG MSI #'+str(row.get('providerNoticeId', FEATURE_ID)),
        'source': SOURCE, 'sourceFamily': 'NAVCEN_MSI', 'areaId': row.get('areaId'),
        'status': row.get('status', 'UNREVIEWED'), 'sourceFirstReceivedAt': row.get('sourceFirstReceivedAt') or row.get('availableAt'),
        'extractionMode': 'HISTORICAL_EXTRACTION_UNAVAILABLE', 'extractionStatus': 'UNSUPPORTED',
        'sourceStatus': 'UNAVAILABLE', 'checkedAt': extracted_at, 'calculationSupported': False,
        'windows': [], 'reason': failure_reason+'; retained complete original unavailable or corrupt'} for row in previous]


def refresh_all(force=False):
    with LOCK:
        from src.portwatch_os.deployment import resolve_mode
        now = wall_now(); received = now.isoformat()
        if resolve_mode(None)[0] not in ('DEMO', 'RESEARCH'):
            return {'sourceFamily': 'NAVCEN_MSI', 'source': SOURCE, 'notices': [], 'sourceStatus': 'UNAVAILABLE',
                'checkedAt': received, 'sourceRegistry': registry(),
                'reason': 'Reviewed NAVCEN integration is limited to noncommercial research/demo use'}
        root = ROOT/'operational_notices'; root.mkdir(parents=True, exist_ok=True)
        pointer = root/'navcen-catalogue-latest.json'
        old = json.loads(pointer.read_text()) if pointer.exists() else None
        legacy = root/'navcen-53842-latest.json'
        previous = old.get('notices', []) if old else ([json.loads(legacy.read_text())] if legacy.exists() else [])
        migration_needed = bool(previous) and any(not row.get('noticeId') for row in previous)
        if old and not force and not migration_needed and now-instant(old['checkedAt']) < TTL:
            return {**old, 'notices': [_lifecycle(n, now) for n in previous]}
        prior = {str(n.get('providerNoticeId', FEATURE_ID)): n for n in previous}; digest = None
        try:
            response = requests.get(SOURCE, timeout=(5, 20)); response.raise_for_status()
            raw = response.content; digest = hashlib.sha256(raw).hexdigest(); original = root/(digest+'.response')
            if original.exists() and hashlib.sha256(original.read_bytes()).hexdigest() != digest:
                raise ValueError('Retained source hash mismatch')
            if not original.exists(): original.write_bytes(raw)
            notices = []
            for facts in discover(raw):
                uid = facts['providerNoticeId']; before = prior.get(uid)
                semantic = hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest(); revision = semantic
                if before and before.get('semanticRevisionId', before.get('revisionId')) == semantic:
                    revision = before['revisionId']
                elif before and (root/(semantic+'.json')).exists():
                    revision = hashlib.sha256(json.dumps([semantic, before.get('revisionId') if before else None, received]).encode()).hexdigest()
                path = root/(revision+'.json')
                if not path.exists():
                    path.write_text(json.dumps({**facts, 'revisionId': revision, 'semanticRevisionId': semantic, 'id': revision,
                        'previousRevisionId': before.get('revisionId') if before else None,
                        'source': SOURCE, 'catalogueSource': CATALOGUE, 'responseSha256': digest,
                        'availableAt': received, 'availabilityBasis': 'First successful PortWatch receipt of this extracted revision'}, indent=2))
                notices.append(_lifecycle({**json.loads(path.read_text()), 'checkedAt': received,
                    'latestResponseSha256': digest, 'sourceStatus': 'CURRENT'}, now))
            seen = {n['providerNoticeId'] for n in notices}
            for uid, before in prior.items():
                if uid not in seen:
                    notices.append({**before, 'providerNoticeId': uid, 'sourceStatus': 'MISSING', 'discoveryStatus': 'MISSING',
                        'checkedAt': received, 'calculationSupported': False,
                        'reason': 'Absent from latest received product; absence is not cancellation or proof of non-occurrence'})
            latest = {'sourceFamily': 'NAVCEN_MSI', 'source': SOURCE, 'checkedAt': received, 'sourceStatus': 'CURRENT',
                'responseSha256': digest, 'reason': None, 'extractionVersion': EXTRACTION_VERSION,
                'sourceRegistry': registry(), 'notices': sorted(notices, key=lambda n: n['providerNoticeId'])}
        except (requests.RequestException, ValueError, KeyError, TypeError, OSError) as exc:
            failed_notices = _hydrate_retained(root, previous, received, str(exc)[:180]) if migration_needed else [
                {**n, 'sourceStatus': 'UNAVAILABLE', 'calculationSupported': False, 'checkedAt': received,
                    'reason': str(exc)[:180]} for n in previous]
            latest = {**(old or {}), 'sourceFamily': 'NAVCEN_MSI', 'source': SOURCE, 'sourceRegistry': registry(),
                'sourceStatus': 'UNAVAILABLE', 'checkedAt': received, 'reason': str(exc)[:180], 'notices': failed_notices}
        with (root/'navcen-receipts.jsonl').open('a') as stream:
            stream.write(json.dumps({'receivedAt': received, 'source': SOURCE, 'responseSha256': digest,
                'sourceStatus': latest['sourceStatus'], 'reason': latest.get('reason'),
                'noticeRevisions': {n.get('providerNoticeId', str(FEATURE_ID)): n.get('revisionId') for n in latest['notices']}})+'\n')
        _write(pointer, latest)
        default = next((n for n in latest['notices'] if n.get('providerNoticeId') == str(FEATURE_ID)), None)
        if default: _write(legacy, default)
        return latest


def refresh(force=False, notice_id=None):
    result = refresh_all(force=force)
    uid = str(notice_id if notice_id is not None else FEATURE_ID).split(':')[-1]
    return next((n for n in result['notices'] if n.get('providerNoticeId') == uid), {
        'noticeRef': 'USCG MSI #'+uid, 'providerNoticeId': uid, 'noticeId': 'NAVCEN_MSI:'+uid,
        'sourceFamily': 'NAVCEN_MSI', 'source': SOURCE, 'windows': [], 'sourceStatus': 'UNAVAILABLE',
        'checkedAt': result['checkedAt'], 'calculationSupported': False,
        'reason': result.get('reason') or 'Notice not discovered; absence is not cancellation'})


def planned_consequence(notice, plan):
    if notice.get('sourceStatus') != 'CURRENT' or notice.get('status') != 'SCHEDULED' or not notice.get('calculationSupported', True):
        raise ValueError('Current reviewed restriction required')
    area_id = notice.get('areaId')
    if not area_id or plan.get('areaId') != area_id or area_id not in plan.get('route', []):
        raise ValueError('Explicit declared bridge passage required; destination membership is insufficient')
    if plan.get('openingRequired') is not True or plan.get('emergencyTransit') is not False:
        raise ValueError('This ordinary opening-requiring passage calculation does not apply to under-bridge or emergency transit')
    requested = instant(plan['passageAt'])
    window = next((w for w in notice['windows'] if instant(w['start']) <= requested < instant(w['end'])), None)
    if not window: raise ValueError('Passage does not overlap this explicit restriction; no waiting asserted')
    if plan.get('timezoneAssumption') != window['timeZone']:
        raise ValueError('Explicit confirmation of the unstated local-zone planning assumption required')
    wait = (instant(window['end'])-requested).total_seconds()/3600
    return {'sourceFamily': 'NAVCEN_MSI', 'window': window, 'requestedPassage': requested.isoformat(),
        'earliestScheduledAccess': window['end'], 'actualEarliestPermittedAccess': None,
        'calculatedWaitHours': wait, 'totalScheduleShiftHours': wait, 'status': 'CONDITIONAL_SCHEDULE_CALCULATION',
        'condition': notice['confirmation']+' Time-zone conversion uses the explicitly confirmed geographic assumption.'}


def require_revision(basis):
    uid = basis.get('reportedFact', {}).get('providerNoticeId')
    latest = refresh(notice_id=uid) if uid and str(uid) != str(FEATURE_ID) else refresh()
    if latest.get('sourceStatus') != 'CURRENT' or latest.get('status') != 'SCHEDULED':
        raise ValueError('Authority restriction unavailable or cancelled; further action blocked')
    if latest['revisionId'] != basis['restriction']['revisionId']:
        raise ValueError('Authority restriction revised; explicitly refresh a linked successor')
    if (wall_now() > instant(latest['checkedAt'])+TTL
            or (latest.get('productThrough') and wall_now() >= instant(latest['productThrough']))
            or (latest.get('windows') and all(instant(w['end']) <= wall_now() for w in latest['windows']))):
        raise ValueError('Authority receipt or product validity expired')
    digest = basis['reportedFact']['responseSha256']; path = ROOT/'operational_notices'/(digest+'.response')
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('Original authority evidence unavailable or corrupt')
    return latest
