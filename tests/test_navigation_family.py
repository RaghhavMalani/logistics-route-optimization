"""Historical public extraction replay and synthetic collector lifecycle checks.

These fixtures establish software behavior, not prospective predictive accuracy.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import copy
import hashlib
import json
import pytest
from src.portwatch_os import clock
from src.portwatch_os.fabric.model import MODE_ENV
from src.portwatch_os.intelligence import navigation_restrictions as n
from src.portwatch_os.intelligence.source_registry import registry

RAW = Path(__file__).parent/'fixtures/navigation_restrictions/navcen-msi-20261014.geojson'
NOW = datetime(2026, 10, 16, 5, tzinfo=timezone.utc)


def product(*ids):
    source = json.loads(RAW.read_bytes())
    return {**source, 'features': [f for f in source['features'] if f['properties']['MSI_UID'] in ids]}


def data(value):
    return json.dumps(value).encode()


def test_retained_original_multiple_distinct_notices_and_asset_scoped_calculation():
    assert hashlib.sha256(RAW.read_bytes()).hexdigest() == '9ee303695c67f57dc69d3c5089e94bc72f3ab6a1342184f82e43e9e3c65128d7'
    notices = {v['providerNoticeId']: v for v in n.discover(RAW.read_bytes())}
    assert len(notices) == 358
    assert {v['areaId'] for v in notices.values() if v['calculationSupported']} == set(n.ASSETS)
    assert notices['53860']['windows'][2]['start'] == '2026-10-20T13:00:00+00:00'
    assert notices['53860']['windows'][2]['end'] == '2026-10-20T21:00:00+00:00'
    assert len(notices['53860']['windows']) == 6  # Alternative dates are not activated.
    mare = {**notices['54726'], 'sourceStatus': 'CURRENT'}
    assert mare['windows'][0]['start'] == '2026-10-17T16:00:00+00:00'
    assert mare['windows'][0]['end'] == '2026-10-17T22:45:00+00:00'
    p = {'areaId': mare['areaId'], 'route': [mare['areaId']], 'openingRequired': True,
        'emergencyTransit': False, 'timezoneAssumption': 'America/Los_Angeles', 'passageAt': '2026-10-17T20:00:00Z'}
    assert n.planned_consequence(mare, p)['calculatedWaitHours'] == 2.75
    assert mare['publishedAt'] is None and mare['providerModifiedAt'] is not None
    construction = notices['42546']
    assert not construction['calculationSupported'] and construction['windows'] == []


def test_new_provider_identity_same_reviewed_asset_not_fixed_feature_filter():
    source = product(53842)
    feature = source['features'][0]; feature['id'] = 99001
    feature['properties']['MSI_UID'] = 99001
    feature['properties']['DESCRIPTION'] = feature['properties']['DESCRIPTION'].replace('MSI #53842', 'MSI #99001').replace('October 17, 2026', 'November 14, 2026')
    feature['properties']['DESCRIPTION'] = feature['properties']['DESCRIPTION'].replace('2026-10-10', '2026-11-01').replace('2026-10-18', '2026-11-30')
    feature['properties']['BEGIN_DATE'] = datetime(2026,11,1,tzinfo=timezone.utc).timestamp()*1000
    feature['properties']['END_DATE'] = datetime(2026,11,30,23,59,59,tzinfo=timezone.utc).timestamp()*1000
    new = n.parse(data(source), 'NAVCEN_MSI:99001')
    assert new['providerNoticeId'] == '99001' and new['areaId'] == n.AREA_ID
    assert new['windows'][0]['start'] == '2026-11-14T09:30:00+00:00'  # DST handled, remains an assumption.
    assert new['windows'][0]['localDate'] == '2026-11-14'


def test_explicit_window_outside_source_envelope_is_not_actionable():
    source = product(53842)
    source['features'][0]['properties']['DESCRIPTION'] = source['features'][0]['properties']['DESCRIPTION'].replace('October 17, 2026', 'November 14, 2026')
    notice = n.discover(data(source))[0]
    assert not notice['calculationSupported'] and not notice['windows']
    assert 'envelope' in notice['reason']


@pytest.mark.parametrize('mutate', [
    lambda f: f['properties'].update(DESCRIPTION=f['properties']['DESCRIPTION']+' The old interval no longer applies.'),
    lambda f: f['properties'].update(DESCRIPTION=f['properties']['DESCRIPTION'].replace('20 feet and 40 feet', '10 feet and 40 feet')),
    lambda f: f['geometry'].update(coordinates=[70, 20]),
    lambda f: f['properties'].update(STATUS='Pending'),
])
def test_changed_unreviewed_prose_geometry_or_status_has_no_stale_semantics(mutate):
    source = product(53842); mutate(source['features'][0])
    notice = n.discover(data(source))[0]
    assert not notice['calculationSupported'] and notice['windows'] == []
    assert notice['extractionStatus'] == 'UNSUPPORTED'


def test_duplicate_identity_is_ambiguous_without_insertion_order_truth():
    source = product(53842); source['features'].append(copy.deepcopy(source['features'][0]))
    source['features'][1]['properties']['DESCRIPTION'] += ' Conflicting record.'
    a = n.discover(data(source))[0]; source['features'].reverse(); b = n.discover(data(source))[0]
    assert a['extractionStatus'] == b['extractionStatus'] == 'AMBIGUOUS'
    assert not a['calculationSupported'] and not b['calculationSupported']
    assert a['windows'] == b['windows'] == []


def test_family_collection_update_missing_cancellation_expiry_and_failure(tmp_path, monkeypatch):
    monkeypatch.setenv(MODE_ENV, 'DEMO'); monkeypatch.setattr(n, 'ROOT', tmp_path)
    moment = [NOW]; monkeypatch.setattr(n, 'wall_now', lambda: moment[0])
    content = [data(product(53842, 53860, 54726))]
    monkeypatch.setattr(n.requests, 'get', lambda *a, **k: SimpleNamespace(content=content[0], raise_for_status=lambda: None))
    first = n.refresh_all(force=True); index = {v['providerNoticeId']: v for v in first['notices']}
    assert len(index) == 3 and all(v['sourceStatus'] == 'CURRENT' for v in index.values())
    assert all(v['availableAt'] == NOW.isoformat() for v in index.values())
    moment[0] += timedelta(minutes=1)
    changed = product(53842, 53860, 54726)
    sr = next(f for f in changed['features'] if f['properties']['MSI_UID'] == 53842)
    sr['properties']['DESCRIPTION'] = sr['properties']['DESCRIPTION'].replace('10:15 a.m.', '11:15 a.m.')
    content[0] = data(changed); second = n.refresh_all(force=True)
    revisions = {v['providerNoticeId']: v for v in second['notices']}
    assert revisions['53842']['previousRevisionId'] == index['53842']['revisionId']
    assert revisions['54726']['revisionId'] == index['54726']['revisionId']
    assert revisions['54726']['availableAt'] == NOW.isoformat()
    changed['features'] = [f for f in changed['features'] if f['properties']['MSI_UID'] != 53842]
    changed['features'][0]['properties']['STATUS'] = 'Cancelled'
    content[0] = data(changed); moment[0] += timedelta(minutes=1)
    third = n.refresh_all(force=True); states = {v['providerNoticeId']: v for v in third['notices']}
    assert states['53842']['sourceStatus'] == 'MISSING' and states['53842']['status'] != 'CANCELLED'
    assert not states['53842']['calculationSupported']
    assert states['53860']['status'] == 'CANCELLED' and not states['53860']['calculationSupported']
    moment[0] = datetime(2026, 10, 18, tzinfo=timezone.utc)
    assert n.refresh(notice_id='54726', force=True)['status'] == 'EXPIRED'
    def fail(*a, **k): raise n.requests.Timeout('Synthetic public provider outage')
    monkeypatch.setattr(n.requests, 'get', fail)
    failed = n.refresh_all(force=True)
    assert failed['sourceStatus'] == 'UNAVAILABLE'
    assert all(v['sourceStatus'] == 'UNAVAILABLE' and not v['calculationSupported'] for v in failed['notices'])
    assert len(list((tmp_path/'operational_notices').glob('*.response'))) == 3
    receipts = (tmp_path/'operational_notices/navcen-receipts.jsonl').read_text().splitlines()
    assert len(receipts) == 5 and json.loads(receipts[-1])['responseSha256'] is None


def test_registry_is_additive_and_investigated_sources_are_not_enabled():
    rows = registry(); nav = next(r for r in rows if r['sourceFamily'] == 'NAVCEN_MSI')
    assert set(nav['assetIds']) == set(n.ASSETS)
    investigated = {'NHO_NAVAREA_VIII', 'JNPA_MARINE_CIRCULAR', 'MPA_PORT_MARINE', 'SCA_NAVIGATION_CIRCULAR'}
    assert all(r['status'] == 'INVESTIGATED_NOT_ENABLED' for r in rows if r['sourceFamily'] in investigated)
    contexts = {r['sourceFamily']: r for r in rows if r['sourceFamily'] in ('PUBLIC_PORT_PDF', 'IMF_PORTWATCH_DAILY')}
    assert set(contexts) == {'PUBLIC_PORT_PDF', 'IMF_PORTWATCH_DAILY'}
    assert all('context' in r['calculationCapability'].lower() for r in contexts.values())
    candidate = next(r for r in rows if r['sourceFamily'] == 'MPA_OCEANS_X')
    assert candidate['status'] == 'DOCS_REVIEWED_AUTHENTICATED_RESPONSE_UNVERIFIED'
    assert candidate['calculationCapability'].startswith('NONE')
    rows.clear(); assert registry()


@pytest.mark.parametrize('catalogue_already_exists', [False, True])
def test_legacy_pointer_403_hydrates_verified_archive_as_historical_and_survives_restart(tmp_path, monkeypatch, catalogue_already_exists):
    monkeypatch.setenv(MODE_ENV, 'DEMO'); monkeypatch.setattr(n, 'ROOT', tmp_path)
    moment = [NOW]; monkeypatch.setattr(n, 'wall_now', lambda: moment[0])
    root = tmp_path/'operational_notices'; root.mkdir()
    raw = RAW.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    (root/(digest+'.response')).write_bytes(raw)
    source_receipt = (NOW-timedelta(days=2)).isoformat()
    legacy = {**n.parse(raw), 'revisionId': 'c'*64, 'responseSha256': digest,
        'availableAt': source_receipt, 'checkedAt': source_receipt, 'sourceStatus': 'CURRENT'}
    legacy.pop('noticeId'); legacy.pop('providerNoticeId')
    (root/'navcen-53842-latest.json').write_text(json.dumps(legacy))
    immutable_old = b'{"legacy":"immutable original revision"}'
    (root/(legacy['revisionId']+'.json')).write_bytes(immutable_old)
    if catalogue_already_exists:
        (root/'navcen-catalogue-latest.json').write_text(json.dumps({'sourceStatus':'UNAVAILABLE',
            'checkedAt':NOW.isoformat(),'notices':[legacy]}))
    attempts = []
    def forbidden(*a, **k):
        attempts.append(True)
        raise n.requests.HTTPError('403 Forbidden synthetic provider response')
    monkeypatch.setattr(n.requests, 'get', forbidden)
    first = n.refresh_all()
    assert first['sourceStatus'] == 'UNAVAILABLE' and len(first['notices']) == 358
    assert all(row['noticeId'].startswith('NAVCEN_MSI:') for row in first['notices'])
    assert all(row['sourceStatus'] == 'UNAVAILABLE' and not row['calculationSupported'] for row in first['notices'])
    assert all(row['extractionMode'] == 'HISTORICAL_EXTRACTION_REPLAY' for row in first['notices'])
    assert all(row['sourceFirstReceivedAt'] == source_receipt and row['availableAt'] == NOW.isoformat() for row in first['notices'])
    reviewed = [row for row in first['notices'] if row.get('historicalCalculationSupported')]
    assert len(reviewed) == 3
    assert (root/(digest+'.response')).read_bytes() == raw
    assert (root/(legacy['revisionId']+'.json')).read_bytes() == immutable_old
    sr = next(row for row in reviewed if row['providerNoticeId'] == '53842')
    assert sr['previousRevisionId'] == legacy['revisionId']
    with pytest.raises(ValueError, match='Current reviewed'):
        n.planned_consequence(sr, {'areaId': n.AREA_ID})
    # Recreate entirely from the durable catalogue/revision files; no process cache.
    moment[0] += timedelta(minutes=20)
    restarted = n.refresh_all()
    assert len(attempts) == 1
    assert [row['revisionId'] for row in restarted['notices']] == [row['revisionId'] for row in first['notices']]
    assert all(row['availableAt'] == NOW.isoformat() and row['sourceFirstReceivedAt'] == source_receipt for row in restarted['notices'])
    moment[0] += timedelta(hours=7)
    retry = n.refresh_all()
    assert len(attempts) == 2 and retry['sourceStatus'] == 'UNAVAILABLE'
    assert all(row['availableAt'] == NOW.isoformat() and not row['calculationSupported'] for row in retry['notices'])


def test_legacy_migration_corrupt_original_keeps_only_blocked_reference(tmp_path, monkeypatch):
    monkeypatch.setenv(MODE_ENV, 'DEMO'); monkeypatch.setattr(n, 'ROOT', tmp_path)
    monkeypatch.setattr(n, 'wall_now', lambda: NOW)
    root = tmp_path/'operational_notices'; root.mkdir()
    row = {'revisionId':'c'*64, 'responseSha256':'b'*64, 'windows':[{'start':'unsafe inherited window'}]}
    (root/'navcen-53842-latest.json').write_text(json.dumps(row))
    (root/('b'*64+'.response')).write_bytes(b'corrupt')
    monkeypatch.setattr(n.requests, 'get', lambda *a, **k: (_ for _ in ()).throw(n.requests.HTTPError('403')))
    result = n.refresh_all(force=True)
    assert result['sourceStatus'] == 'UNAVAILABLE' and len(result['notices']) == 1
    blocked = result['notices'][0]
    assert blocked['noticeId'] == 'NAVCEN_MSI:53842'
    assert blocked['extractionStatus'] == 'UNSUPPORTED' and blocked['windows'] == []
    assert not blocked['calculationSupported'] and 'corrupt' in blocked['reason']


@pytest.mark.parametrize('coordinates', [None, [], [20], ['bad', 34], [float('nan'), 34], [float('inf'), 34], [181, 34], [20, -91]])
def test_unknown_or_invalid_source_point_is_null_and_whole_catalogue_stays_json_safe(coordinates):
    source = product(53842, 54726)
    first = source['features'][0]
    first['geometry']['coordinates'] = coordinates
    first['properties']['TITLE'] = None
    notices = n.discover(data(source))
    invalid = next(v for v in notices if v['providerNoticeId'] == '53842')
    assert invalid['coordinates'] is None and isinstance(invalid['title'], str)
    assert not invalid['calculationSupported']
    json.dumps(notices, allow_nan=False)
    assert next(v for v in notices if v['providerNoticeId'] == '54726')['calculationSupported']


def test_invalid_date_metadata_is_inspectable_unsupported_record_not_whole_product_failure():
    source = product(53842, 54726)
    source['features'][0]['properties']['MODIFIED_DATE'] = float('nan')
    source['features'].append({'properties': 'malformed unidentified record'})
    notices = n.discover(data(source))
    bad = next(v for v in notices if v['providerNoticeId'] == '53842')
    assert bad['extractionStatus'] == 'UNSUPPORTED' and bad['coordinates'] is None
    assert isinstance(bad['title'], str) and bad['sourceFeature']['properties']['MODIFIED_DATE'] is None
    json.dumps(notices, allow_nan=False)
    assert len(notices) == 2
