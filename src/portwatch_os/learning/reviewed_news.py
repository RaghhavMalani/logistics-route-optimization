"""One reviewed announcement family on the existing reconciliation worker.

GAC's Eastham report is checked against the original Peel Ports notice. Only
announced calendar closure periods are supported, not whole-canal closure,
vessel suitability, actual occurrence, or a shipping consequence.
"""
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

import requests

from src.portwatch_os.clock import wall_now
from src.portwatch_os.intelligence.current_environment import ROOT
from src.portwatch_os.learning import shared_feedback as feedback

SOURCE = 'https://www.gac.com/hot-port-news/upcoming-lock-closures'
FAMILY = 'GAC_EASTHAM_NOTICE_ANNOUNCEMENT_V1'
PARSER_VERSION = 'gac-eastham-announcement-v1'
REFERENCE = 'MNTM 2026-18'
LINEAGE = 'Peel Ports:MNTM 2026-18'
ENTITY = 'EASTHAM_80_LOCK'
GEOGRAPHY = 'Eastham 80-foot Lock, Manchester Ship Canal'
MODE = 'PRIMARY_DOCUMENT_ATTESTS_ATTRIBUTED_ANNOUNCEMENT'
PREDICATE = 'AUTHORITY_NOTICE_ANNOUNCED_LOCK_CLOSURE'
MONTHS = '(?:September|October|November)'


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, value):
        if not self.skip:
            self.parts.append(value)


def parse_gac_eastham(raw):
    """Strict endpoint-specific extraction, not a general headline parser."""
    if not isinstance(raw, bytes) or len(raw) > 4_000_000:
        raise ValueError('Supported GAC article original required')
    parser = _Text()
    parser.feed(raw.decode('utf-8-sig'))
    text = ' '.join(' '.join(parser.parts).split())
    marker = re.search(r"The Eastham 80[′'] Lock will close to vessel movements", text)
    qualification = 'The Queen Elizabeth II Lock will not be affected by the works.'
    end = text.find(qualification, marker.start() if marker else 0)
    if not marker or end < 0:
        raise ValueError('Supported Eastham announcement or unaffected-lock qualification unavailable')
    body = text[marker.start():end + len(qualification)]
    if re.search(r'\b(?:cancelled|canceled|withdrawn|postponed|rescinded)\b', body, re.I):
        raise ValueError('Unreviewed cancellation or qualification; original retained')
    pattern = re.compile(
        rf'({MONTHS})\s+(\d{{1,2}})[–-](\d{{1,2}}),?\s+(2026)\s*[-–]?\s*'
        rf'Last operational tide:\s*(\d{{2}}\.\d{{2}})\s*\((BST|GMT)\)\s*HW on\s*'
        rf'({MONTHS})\s+(\d{{1,2}}),?\s+(2026)\s*[-–]?\s*'
        rf'First operational tide:\s*(\d{{2}}\.\d{{2}})\s*\((BST|GMT)\)\s*HW on\s*'
        rf'({MONTHS})\s+(\d{{1,2}}),?\s+(2026)')
    matches = pattern.findall(body)
    if len(matches) != 3:
        raise ValueError('Expected three explicit 2026 Eastham closure periods and operational tides')
    def day(month, number, year):
        return datetime.strptime(f'{number} {month} {year}', '%d %B %Y').date()
    def tide(month, number, year, clock, zone):
        local = datetime.combine(day(month, number, year), datetime.strptime(clock, '%H.%M').time())
        return local.replace(tzinfo=timezone(timedelta(hours=1 if zone == 'BST' else 0))).astimezone(timezone.utc).isoformat()
    windows = []
    for month, start, ending, year, last_time, last_zone, last_month, last_day, last_year, first_time, first_zone, first_month, first_day, first_year in matches:
        beginning, end_day = day(month, start, year), day(month, ending, year)
        if end_day < beginning:
            raise ValueError('Invalid closure calendar period')
        last = tide(last_month, last_day, last_year, last_time, last_zone)
        first = tide(first_month, first_day, first_year, first_time, first_zone)
        if feedback.instant(last).date() > beginning or feedback.instant(first).date() <= end_day:
            raise ValueError('Operational tides do not bracket the calendar period')
        windows.append({'closureStartDate': beginning.isoformat(), 'closureEndDate': end_day.isoformat(),
                        'lastOperationalTide': last, 'firstOperationalTide': first})
    if len({row['closureStartDate'] for row in windows}) != 3:
        raise ValueError('Duplicate or conflicting closure periods')
    return {'version': PARSER_VERSION, 'wording': marker[0], 'windows': windows,
        'publicationTime': None, 'publicationPrecision': 'UNAVAILABLE',
        'exclusions': ['WHOLE_CANAL_CLOSURE_NOT_ASSESSED', 'VESSEL_SUITABILITY_NOT_ASSESSED', 'OPERATIONAL_TIDE_ACCURACY_NOT_SCORED',
                       'ACTUAL_CLOSURE_AND_SHIPPING_EFFECT_NOT_OBSERVED'],
        'attribution': 'GAC Hot Port News; primary announcement from Peel Ports / Manchester Ship Canal Company'}


def _target(window):
    return {'kind': 'ANNOUNCEMENT', 'predicate': PREDICATE, 'authorityNoticeRef': REFERENCE,
        'reportedPeriod': {'from': window['closureStartDate'], 'through': window['closureEndDate'], 'precision': 'DATE_ONLY'}}


def _first_receipt(store, digest, source, default):
    rows = [row['receivedAt'] for row in store.feedback('receipt')
        if row.get('responseSha256') == digest and row.get('source') == source
        and feedback.instant(row['receivedAt']) <= feedback.instant(default)]
    return min(rows, key=feedback.instant) if rows else default


def collect_gac_eastham(store, raw, received, notice, *, root=ROOT, interpreted_at=None):
    """Append immutable derived claims, with distinct receipt/extraction times."""
    from src.portwatch_os.learning.intelligence_reconciliation import retain_response
    digest = retain_response(store, raw, SOURCE, received, root, product=FAMILY,
                             request_metadata={'method': 'GET', 'url': SOURCE, 'parserVersion': PARSER_VERSION})
    parsed = parse_gac_eastham(raw)
    available = max(feedback.instant(received), feedback.instant(interpreted_at or wall_now().isoformat())).isoformat()
    revision = feedback.identifier([PARSER_VERSION, parsed])
    base = {'kind': 'REPORTED_FACT', 'wording': parsed['wording'], 'value': True,
        'entity': ENTITY, 'geography': GEOGRAPHY, 'originAt': available, 'firstAvailableAt': available,
        'sourceFirstReceivedAt': _first_receipt(store, digest, SOURCE, received), 'interpretedAt': available,
        'publishedAt': None, 'publicationPrecision': 'UNAVAILABLE', 'source': SOURCE,
        'sourceVersion': revision, 'sourceRevisionId': revision, 'sourceReportId': SOURCE,
        'responseSha256': digest, 'independenceKey': LINEAGE, 'sourceLineageId': LINEAGE,
        'derivedFrom': LINEAGE, 'attributedAuthorityLineageId': LINEAGE,
        'eventReference': REFERENCE + ':' + ENTITY, 'inputs': [], 'unit': 'boolean',
        'aggregation': 'EXPLICIT_NEWS_TARGET', 'reviewedSourceFamily': FAMILY,
        'sourceRole': 'SECONDARY_ATTRIBUTED_REPORT', 'derivationVersion': PARSER_VERSION,
        'interpretationBasis': 'Versioned calendar closure announcement, not actual occurrence',
        'wordingBasis': 'Exact short source excerpt; full original response retained',
        'independentReportingConfirmations': 0, 'attribution': parsed['attribution']}
    made = []
    for window in parsed['windows']:
        target = _target(window)
        prior = [row for row in store.feedback('claim') if row.get('sourceReportId') == SOURCE
                 and row.get('sourceRevisionId') == revision and row.get('target') == target]
        if prior:
            item = min(prior, key=lambda row: (feedback.instant(row['firstAvailableAt']), row['id']))
        else:
            item = feedback.claim(store, {**base, 'target': target,
                'eventKey': REFERENCE + ':' + window['closureStartDate'], 'reportedSchedule': window})
            store.append_feedback('news-source-quality', {'id': item['id'], 'sourceFamily': FAMILY,
                'sourceProductTimestamp': None, 'timestampMeaning': 'Receipt and interpretation clocks; publication time unavailable',
                'articleBodyRetained': True, 'sourceProductRetained': True, 'derivationVersion': PARSER_VERSION,
                'supportedPredicate': PREDICATE, 'assessedScope': 'Announced calendar closure period only; operational tide accuracy is not scored',
                'originalAccess': 'LOCAL_RESEARCH_ARCHIVE',
                'redistributionPolicy': 'Full-response republication not established; attributed excerpt and extracted facts only',
                'closureInference': 'Only the announced lock calendar period is assessed; actual closure and whole-canal restriction remain unverified',
                'deduplication': 'One Peel Ports announcement lineage; GAC is another document, not independent occurrence evidence',
                'exclusions': parsed['exclusions'], 'attribution': parsed['attribution']})
        made.append(item)
    collect_primary_notice_state(store, notice, interpreted_at=available)
    for item in made:
        feedback.verify_news(store, item, available)
    return made


def collect_primary_notice_state(store, notice, *, interpreted_at=None):
    """Retain exact primary announcement/cancellation independently of GAC fetch.

    A cancellation changes applicability of an attributed announcement. It
    never supplies false announcement truth or proves actual non-occurrence.
    """
    if not notice or notice.get('noticeRef') != REFERENCE or not notice.get('revisionId') or not notice.get('pdfSha256'):
        return []
    from src.portwatch_os.intelligence import operational_notices
    original = Path(operational_notices.ROOT) / 'operational_notices' / (notice['pdfSha256'] + '.response')
    if not original.is_file() or hashlib.sha256(original.read_bytes()).hexdigest() != notice['pdfSha256']:
        raise ValueError('Primary authority original unavailable or corrupt')
    retained = operational_notices.parse_eastham(original.read_bytes())
    canonical_revision = hashlib.sha256(json.dumps(retained, sort_keys=True).encode()).hexdigest()
    if any(notice.get(key) != value for key, value in retained.items()) or notice['revisionId'] != canonical_revision:
        raise ValueError('Primary interpretation does not match its original')
    available = max(feedback.instant(notice['availableAt']), feedback.instant(interpreted_at or wall_now().isoformat())).isoformat()
    if retained.get('status') == 'CANCELLED':
        records = [(item['target'], item['eventKey'], item['sourceVersion']) for item in store.feedback('claim')
                   if item.get('reviewedSourceFamily') == FAMILY and item.get('sourceRole') == 'SECONDARY_ATTRIBUTED_REPORT']
    elif retained.get('areaId') == ENTITY and retained.get('status') == 'SCHEDULED':
        records = [(_target(window), REFERENCE + ':' + window['closureStartDate'], None) for window in retained.get('windows', [])]
    else:
        return []
    made = []
    for target, event_key, cancelled_version in records:
        kind = 'CANCELLATION' if cancelled_version else 'AUTHORITY_RECORD'
        prior = [row for row in store.feedback('evidence') if row.get('reviewedSourceFamily') == FAMILY
                 and row.get('sourceRevisionId') == notice['revisionId'] and row.get('target') == target
                 and row.get('recordKind') == kind and row.get('cancelsSourceVersion') == cancelled_version]
        if prior:
            made.append(prior[0]); continue
        body = {'eventKey': event_key, 'eventReference': REFERENCE + ':' + ENTITY,
            'entity': ENTITY, 'geography': GEOGRAPHY, 'target': target,
            'value': None if cancelled_version else True, 'unit': 'boolean', 'aggregation': 'EXPLICIT_NEWS_TARGET',
            'source': notice.get('pdfSource') or operational_notices.PDF, 'sourceVersion': notice['revisionId'],
            'sourceRevisionId': notice['revisionId'], 'sourceReportId': REFERENCE, 'sourceLineageId': LINEAGE,
            'independenceKey': LINEAGE, 'reviewedSourceFamily': FAMILY,
            'sourceRole': 'PRIMARY_AUTHORITY_NOTICE', 'verificationMode': MODE,
            'recordKind': kind, 'responseSha256': notice['pdfSha256'],
            'firstAvailableAt': available, 'interpretedAt': available,
            'sourceFirstReceivedAt': notice['availableAt'], 'observedAt': notice['availableAt'],
            'observationTimeMeaning': 'Legacy evidence clock is source receipt, not closure or measurement time',
            'publishedDate': retained.get('publishedDate'), 'publicationPrecision': 'DATE_ONLY',
            'derivationVersion': PARSER_VERSION, 'independentReportingConfirmations': 0,
            'scope': 'Primary document attests announcement/applicability only; not independent reporting, occurrence or shipping effects'}
        if cancelled_version:
            body['cancelsSourceVersion'] = cancelled_version
        made.append(feedback.evidence(store, body))
    for item in store.feedback('claim'):
        if (item.get('reviewedSourceFamily') == FAMILY
                and feedback.instant(item['firstAvailableAt']) <= feedback.instant(available)):
            feedback.verify_news(store, item, available)
    return made


def refresh_gac_eastham(store, notice, *, root=ROOT):
    """One bounded fetch called by the existing six-hour worker; no scheduler."""
    checked = wall_now().isoformat()
    try:
        primary_count = len(collect_primary_notice_state(store, notice))
        primary_status = 'RETAINED' if primary_count else 'NO_SUPPORTED_PRIMARY'
    except (ValueError, OSError, KeyError):
        primary_count, primary_status = 0, 'ORIGINAL_OR_INTERPRETATION_UNAVAILABLE'
    try:
        response = requests.get(SOURCE, timeout=(4, 20))
        response.raise_for_status()
        final = urlparse(response.url)
        if final.scheme != 'https' or final.hostname != 'www.gac.com' or final.path.rstrip('/') != '/hot-port-news/upcoming-lock-closures':
            raise ValueError('Unsupported GAC redirect')
        received = wall_now().isoformat()
        claims = collect_gac_eastham(store, response.content, received, notice, root=root)
        state = {'status': 'RETAINED', 'source': SOURCE, 'checkedAt': checked,
                 'receivedAt': received, 'claimsCollected': len(claims), 'reason': None}
    except (requests.RequestException, ValueError, OSError, KeyError) as exc:
        state = {'status': 'UNAVAILABLE', 'source': SOURCE, 'checkedAt': checked, 'claimsCollected': 0,
            'reason': 'Public article original unavailable or unsupported; retained claims are not replaced',
            'failureKind': 'HTTP_' + str(exc.response.status_code) if isinstance(exc, requests.HTTPError) and exc.response is not None else
                'PROVIDER_UNAVAILABLE' if isinstance(exc, requests.RequestException) else 'ORIGINAL_OR_EXTRACTION_UNAVAILABLE'}
    state.update(primaryEvidenceStatus=primary_status, primaryEvidenceRecords=primary_count)
    store.append_feedback('reviewed-news-source-check', {**state, 'id': feedback.identifier(state),
        'sourceFamily': FAMILY, 'derivationVersion': PARSER_VERSION,
        'meaning': 'Collection check only; not an observation, assessment or operational target'})
    return state
