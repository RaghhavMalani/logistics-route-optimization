"""Retained public DTO, temporal refusal and actual AIS normalizer contracts.

Network responses are explicit fixtures; these tests do not prove live coverage.
"""
import copy,json
from datetime import datetime,timedelta,timezone
from unittest.mock import Mock
import pytest
import requests
from src.portwatch_os.intelligence import free_sources as sources
from src.portwatch_os.intelligence import current_environment as environment
from src.portwatch_os.fabric.ais import client as ais
from tests.test_ais_ingest import position
from src.portwatch_os.decision.commercial import CommercialContext,resource_conflicts
from tests.test_commercial_shadow import example,AT,simulation
from src.portwatch_os.decision.commercial_uncertainty import simulate


def response(body):
    r=Mock();r.content=body;r.raise_for_status.return_value=None
    return r


def test_reference_date_first_availability_and_failed_check_do_not_become_current(tmp_path,monkeypatch):
    monkeypatch.setattr(sources,'ROOT',tmp_path)
    now=AT
    monkeypatch.setattr(sources,'wall_now',lambda:now)
    monkeypatch.setattr(sources,'world_now',lambda:now)
    monkeypatch.setattr(sources.requests,'get',lambda *a,**kw:response(b'observation_date,DEXINUS\n2026-10-01,83.5\n'))
    first=sources.collect('fred_fx');assert first['ok']
    row=sources.public_product('fred_fx',AT)
    assert row['freshness']=='STALE' and row['rows'][0]['date']=='2026-10-01'
    assert row['publishedAt'] is None and row['timePrecision']=='DATE_ONLY'
    now=AT+timedelta(hours=1)
    same=sources.collect('fred_fx');assert same['firstAvailableAt']==first['firstAvailableAt']
    assert same['lastSuccessfulCheckAt']!=first['lastSuccessfulCheckAt']
    monkeypatch.setattr(sources.requests,'get',lambda *a,**kw:(_ for _ in ()).throw(requests.Timeout('software outage')))
    assert not sources.collect('fred_fx')['ok']
    retained=sources.public_product('fred_fx',now)
    assert retained['lastSuccessfulCheckAt']==same['lastSuccessfulCheckAt'] and retained['error']=='Timeout'
    assert sources.public_product('fred_fx',AT-timedelta(seconds=1))['rows']==[]
    assert 'request' not in row and str(tmp_path) not in str(row)


def test_unqualified_parse_retains_original_and_cannot_refresh_success(tmp_path,monkeypatch):
    monkeypatch.setattr(sources,'ROOT',tmp_path);monkeypatch.setattr(sources,'wall_now',lambda:AT)
    monkeypatch.setattr(sources.requests,'get',lambda *a,**kw:response(b'observation_date,DEXINUS\n2026-10-30,83.5\n'))
    first=sources.collect('fred_fx');assert first['ok']
    monkeypatch.setattr(sources.requests,'get',lambda *a,**kw:response(b'<html>provider failure</html>'))
    assert not sources.collect('fred_fx')['ok']
    row=sources.public_product('fred_fx',AT)
    assert row['sha256']==first['sha256'] and row['lastSuccessfulCheckAt']==first['lastSuccessfulCheckAt']
    assert row['freshness']=='STALE' and list((tmp_path/'unqualified').glob('*.response'))
    assert len(list((tmp_path/'archive').glob('*.response')))==1


def test_discovery_duplicates_no_invented_probability_and_aggregate_date_precision():
    articles=[{'url':'https://example.org/notice','title':'Maritime report','seendate':'20261101T100000Z'}]*2
    rows=sources._parse('gdelt',json.dumps({'articles':articles}).encode())
    assert len(rows)==1 and 'probability' not in rows[0] and 'closure' not in rows[0]
    row=sources._parse('imf',json.dumps({'features':[{'attributes':{'portid':'port883','date':'2026-10-01','portcalls':4}}]}).encode())[0]
    assert row['date']=='2026-10-01' and row['portcalls']==4


def test_weather_projection_and_original_first_availability_are_read_only(tmp_path,monkeypatch):
    from src.utils import port_registry
    port=port_registry.resolve('INNSA');monkeypatch.setattr(environment,'ROOT',tmp_path)
    monkeypatch.setattr(environment.requests,'get',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('Projection made a provider request')))
    assert environment.retained_bundle(port)['hourly']==[]
    before=list(tmp_path.rglob('*'))
    environment.map_signals()
    assert list(tmp_path.rglob('*'))==before


def test_public_ais_no_key_connection_is_not_coverage_and_reader_does_not_start(monkeypatch):
    monkeypatch.setattr(ais,'_CLIENT',None)
    monkeypatch.setattr(ais,'get_client',lambda:(_ for _ in ()).throw(AssertionError('A read started a client')))
    result=ais.public_observations(now=AT)
    assert result['count']==0 and result['freshness']=='UNAVAILABLE'
    assert result['traffic']['mode']=='UNAVAILABLE' and result['tracks']==[]


def test_public_ais_real_normalizer_sentinels_unknown_time_age_and_no_private_identity(monkeypatch):
    client=ais.AisStreamClient(api_key='fixture-secret-never-public')
    envelope=position(at=AT,TrueHeading=511,Cog=360.,Sog=102.3)
    envelope['MetaData'].pop('time_utc');envelope['Message']['PositionReport']['Timestamp']=12
    client.feed(envelope,now=AT);monkeypatch.setattr(ais,'_CLIENT',client)
    result=ais.public_observations(now=AT)
    assert result['freshness']=='CURRENT' and result['count']==1
    row=result['tracks'][0];fix=row['latest']
    assert row['name'] is None and row['imo'] is None and row['destinationText'] is None
    assert fix['headingDegrees'] is None and fix['cogDegrees'] is None and fix['sogKnots'] is None
    assert fix['sourceTimestamp'] is None and not fix['provenance']['source_time_known']
    assert fix['ingestedAt']==AT.isoformat() and fix['rawRef'].startswith('ais-observation:')
    assert 'fixture-secret' not in str(result) and 'META NAME' not in str(result)
    assert ais.public_observations(now=AT+timedelta(minutes=11))['freshness']=='STALE'
    assert ais.public_observations(now=AT+timedelta(hours=2))['tracks']==[]


def test_public_ais_replay_is_historical_not_a_live_stream(monkeypatch):
    client=ais.AisStreamClient(api_key='fixture-key');client.feed(position(at=AT),now=AT)
    client.status.replay_of='fixture-recording';monkeypatch.setattr(ais,'_CLIENT',client)
    r=ais.public_observations(now=AT)
    assert r['freshness']=='HISTORICAL' and r['traffic']['mode']=='AIS_STALE'


def test_three_shared_resource_claims_sweep_capacity_without_pairwise_undercount():
    c,_=example();basis=c['basis']
    claim=dict(resourceId='fixture-slot',unit='TEU',quantity='4',capacity='10',beginsAt='2026-11-02T01:00:00Z',endsAt='2026-11-02T02:00:00Z',basis=basis)
    c['resources']=[claim];other=copy.deepcopy(c);other['voyageId']='v2';third=copy.deepcopy(c);third['voyageId']='v3'
    rows=resource_conflicts(CommercialContext(**c),[other,third])
    assert rows[0]['status']=='CONFLICT' and rows[0]['claimedQuantity']=='12'
    other['resources'][0]['beginsAt']='2026-11-02T02:00:00Z';other['resources'][0]['endsAt']='2026-11-02T03:00:00Z'
    assert all(r['status']=='UNRESERVED_WITHIN_DECLARED_CAPACITY' for r in resource_conflicts(CommercialContext(**c),[other]))
    c['resources'][0]['capacity']=None
    assert resource_conflicts(CommercialContext(**c),[])[0]['status']=='CAPACITY_UNKNOWN'


def test_declared_mean_tail_preference_can_switch_choice_without_changing_sampled_world():
    c,p=example();s=c['consignments'][0]
    s.update(required=False,deliveryOffsetHours='0',deadline='2026-11-02T20:00:00Z',penalty=dict(payer='carrier',beneficiary='owner',ratePerHour={'amount':'100','currency':'USD'},cap={'amount':'500','currency':'USD'},contractBasis='Illustrative capped penalty'))
    c['charges'][0].update(kind='FIXED_COMPONENT',optionAmounts={'keep':{'amount':'100','currency':'USD'},'slow':{'amount':'0','currency':'USD'}})
    c['materialComponents'].append('penalty:s1')
    config=simulation((0,10),(.9,.1));config.draws=4096;config.alpha=.9;config.tailPreference=0
    mean=simulate(CommercialContext(**c),p,AT,config)
    config.tailPreference=1
    tail=simulate(CommercialContext(**c),p,AT,config)
    assert mean['worldSampleHash']==tail['worldSampleHash']
    assert mean['conditionalShadowPick']=='slow' and tail['conditionalShadowPick']=='keep'
    assert mean['independentOperationalTargets']==0
