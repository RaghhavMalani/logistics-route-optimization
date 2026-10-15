"""Reviewed NAVCEN MSI bridge notice, not a generic closure text classifier.

Missing features or changed semantics block continuation. A scheduled opening
does not prove that a bridge opened or that this vessel obtained clearance.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import threading
from zoneinfo import ZoneInfo
import requests
from src.portwatch_os.clock import wall_now
from src.portwatch_os.intelligence.current_environment import ROOT, instant

SOURCE = 'https://www.navcen.uscg.gov/sites/default/files/msi/bridge_1.geojson'
CATALOGUE = 'https://www.navcen.uscg.gov/msi'
FEATURE_ID = 53842
AREA_ID = 'WRIGHTSVILLE_SR74'
TTL = timedelta(hours=6)
LOCK = threading.RLock()


def parse(raw):
    product = json.loads(raw)
    features = [f for f in product['features'] if f['properties'].get('MSI_UID') == FEATURE_ID]
    if len(features) != 1:
        raise ValueError('Reviewed MSI feature absent or ambiguous; absence is not cancellation')
    feature = features[0]; props = feature['properties']; text = props['DESCRIPTION']
    if feature['geometry']['type'] != 'Point' or props['SUB_CATEGORY'] != 'Bridges':
        raise ValueError('Reviewed bridge geometry/category changed')
    lon, lat = feature['geometry']['coordinates']
    if abs(lon + 77.81259) > .001 or abs(lat - 34.21828) > .001:
        raise ValueError('Reviewed bridge location changed; geographic review required')
    status = props['STATUS']
    cancelled = status.lower() in ('cancelled', 'canceled', 'withdrawn')
    if not cancelled and status != 'Approved':
        raise ValueError('Reviewed notice is not approved')
    match = re.search(r'S\.R\. 74 \(Wrightsville Beach\) Bridge will be maintained in the closed-to-navigation position from (\d{1,2}:\d{2}) a\.m\. to (\d{1,2}:\d{2}) a\.m\. on (\w+ \d{1,2}, \d{4})', text)
    if not cancelled and (not match or not all(t in text for t in (
        '20 feet and 40 feet, respectively, above mean high water',
        'Vessels able to pass through the bridges in the closed-to-navigation position may do so at anytime.',
        'at least 15 minutes notice'))):
        raise ValueError('Restriction, exemption or emergency semantics changed; adapter review required')
    windows = []
    if not cancelled:
        day = datetime.strptime(match[3], '%B %d, %Y').date()
        # The MSI body supplies local clock values without a zone. This explicit
        # geographic planning assumption is displayed and confirmed by the user.
        def utc(clock):
            return datetime.combine(day, datetime.strptime(clock, '%H:%M').time(),
                ZoneInfo('America/New_York')).astimezone(timezone.utc).isoformat()
        windows = [{'start':utc(match[1]), 'end':utc(match[2]), 'localStart':match[1], 'localEnd':match[2],
                    'localDate':day.isoformat(), 'timeZone':'America/New_York',
                    'timeZoneBasis':'OPERATOR_CONFIRMED_GEOGRAPHIC_ASSUMPTION; zone not stated in MSI body',
                    'calculationSupported':True}]
    def metadata(key):
        value = props.get(key)
        return datetime.fromtimestamp(value/1000, timezone.utc).isoformat() if isinstance(value, (int,float)) else None
    return {'sourceFamily':'NAVCEN_MSI', 'noticeRef':'USCG MSI #53842', 'areaId':AREA_ID,
        'title':'S.R. 74 Wrightsville Beach bridge opening restriction', 'area':'Atlantic Intracoastal Waterway at Wrightsville Beach, North Carolina',
        'coordinates':{'lon':lon,'lat':lat,'basis':'Official MSI point; not a surveyed navigation chart or complete route'},
        'status':'CANCELLED' if cancelled else 'SCHEDULED', 'publisherStatus':status, 'windows':windows,
        'originalWording':text, 'issuer':'U.S. Coast Guard / NAVCEN',
        'providerCreatedAt':metadata('CREATE_DATE'), 'providerModifiedAt':metadata('MODIFIED_DATE'),
        'publicationPrecision':'PROVIDER_RECORD_METADATA; publication instant not established',
        'publishedAt':None, 'productFrom':metadata('BEGIN_DATE'), 'productThrough':metadata('END_DATE'),
        'restriction':'Scheduled closed-to-navigation position, not a closure to vessels able to pass under the closed bridge.',
        'applicability':{'vesselScope':'DECLARED_PASSAGE_REQUIRING_BRIDGE_OPENING',
            'characteristicRule':'Published clearance is 20 ft above mean high water. Declared opening requirement must account for actual water level and clearance; dimensions alone do not prove navigability.'},
        'unaffectedAlternative':'Vessels able to pass beneath the closed bridge may transit at any time. Emergency opening requires at least 15 minutes notice; this comparison assumes ordinary, non-emergency passage.',
        'confirmation':'End of the published closed-position period is a conditional planning boundary, not confirmed opening, clearance or an allocated transit slot.',
        'mechanism':'Explicit declared passage at this bridge, requiring an opening, overlaps the published closed-position interval.'}


def refresh(force=False):
    with LOCK:
        from src.portwatch_os.deployment import resolve_mode
        if resolve_mode(None)[0] not in ('DEMO','RESEARCH'):
            return {'noticeRef':'USCG MSI #53842','sourceFamily':'NAVCEN_MSI','source':SOURCE,'windows':[],
                'sourceStatus':'UNAVAILABLE','checkedAt':wall_now().isoformat(),
                'reason':'Reviewed NAVCEN integration is limited to noncommercial research/demo use'}
        root = ROOT/'operational_notices'; root.mkdir(parents=True, exist_ok=True)
        pointer = root/'navcen-53842-latest.json'
        old = json.loads(pointer.read_text()) if pointer.exists() else None
        if old and not force and wall_now()-instant(old['checkedAt']) < TTL:
            return old
        digest = None
        try:
            response = requests.get(SOURCE, timeout=(5,20)); response.raise_for_status()
            raw = response.content; digest = hashlib.sha256(raw).hexdigest()
            original = root/(digest+'.response')
            if original.exists() and hashlib.sha256(original.read_bytes()).hexdigest() != digest:
                raise ValueError('Retained source hash mismatch')
            if not original.exists(): original.write_bytes(raw)
            facts = parse(raw); received = wall_now().isoformat()
            semantic = hashlib.sha256(json.dumps(facts,sort_keys=True).encode()).hexdigest()
            revision = semantic
            if old and old.get('semanticRevisionId',old.get('revisionId')) == semantic:
                revision = old['revisionId']
            elif (root/(semantic+'.json')).exists():
                # A reversion is a new receipt occurrence with lineage; do not
                # revive a previously superseded claim's old availability.
                revision = hashlib.sha256(json.dumps([semantic,old.get('revisionId') if old else None,received]).encode()).hexdigest()
            path = root/(revision+'.json')
            if not path.exists():
                path.write_text(json.dumps({**facts,'revisionId':revision,'semanticRevisionId':semantic,'id':revision,
                    'previousRevisionId':old.get('revisionId') if old else None,
                    'source':SOURCE,'catalogueSource':CATALOGUE,'responseSha256':digest,
                    'availableAt':received,'availabilityBasis':'First successful PortWatch receipt of this reviewed revision'},indent=2))
            latest = {**json.loads(path.read_text()),'checkedAt':received,'latestResponseSha256':digest,'sourceStatus':'CURRENT','reason':None}
        except (requests.RequestException, ValueError, KeyError, TypeError, OSError) as exc:
            latest = {**(old or {'noticeRef':'USCG MSI #53842','sourceFamily':'NAVCEN_MSI','source':SOURCE,'windows':[]}),
                'sourceStatus':'UNAVAILABLE','checkedAt':wall_now().isoformat(),'reason':str(exc)[:180]}
        with (root/'navcen-receipts.jsonl').open('a') as stream:
            stream.write(json.dumps({'receivedAt':latest['checkedAt'],'revisionId':latest.get('revisionId'),
                'source':SOURCE,'responseSha256':digest,'sourceStatus':latest['sourceStatus'],'reason':latest.get('reason')})+'\n')
        temporary=pointer.with_suffix('.tmp'); temporary.write_text(json.dumps(latest,indent=2)); temporary.replace(pointer)
        return latest


def planned_consequence(notice, plan):
    if notice.get('sourceStatus') != 'CURRENT' or notice.get('status') != 'SCHEDULED':
        raise ValueError('Current reviewed restriction required')
    if plan.get('areaId') != AREA_ID or AREA_ID not in plan.get('route', []):
        raise ValueError('Explicit declared bridge passage required; destination membership is insufficient')
    if plan.get('openingRequired') is not True or plan.get('emergencyTransit') is not False:
        raise ValueError('This ordinary opening-requiring passage calculation does not apply to under-bridge or emergency transit')
    if plan.get('timezoneAssumption') != 'America/New_York':
        raise ValueError('Explicit confirmation of the unstated local-zone planning assumption required')
    requested=instant(plan['passageAt'])
    window=next((w for w in notice['windows'] if instant(w['start']) <= requested < instant(w['end'])),None)
    if not window: raise ValueError('Passage does not overlap this explicit restriction; no waiting asserted')
    wait=(instant(window['end'])-requested).total_seconds()/3600
    return {'sourceFamily':'NAVCEN_MSI','window':window,'requestedPassage':requested.isoformat(),
        'earliestScheduledAccess':window['end'],'actualEarliestPermittedAccess':None,
        'calculatedWaitHours':wait,'totalScheduleShiftHours':wait,'status':'CONDITIONAL_SCHEDULE_CALCULATION',
        'condition':notice['confirmation']+' Time-zone conversion uses the explicitly confirmed geographic assumption.'}


def require_revision(basis):
    latest=refresh()
    if latest.get('sourceStatus') != 'CURRENT' or latest.get('status') != 'SCHEDULED':
        raise ValueError('Authority restriction unavailable or cancelled; further action blocked')
    if latest['revisionId'] != basis['restriction']['revisionId']:
        raise ValueError('Authority restriction revised; explicitly refresh a linked successor')
    if wall_now() > instant(latest['checkedAt'])+TTL or wall_now() >= instant(latest['productThrough']):
        raise ValueError('Authority receipt or product validity expired')
    digest=basis['reportedFact']['responseSha256']; path=ROOT/'operational_notices'/(digest+'.response')
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('Original authority evidence unavailable or corrupt')
    return latest
