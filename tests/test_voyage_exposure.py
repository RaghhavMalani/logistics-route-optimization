"""Synthetic matching regressions; these are not exposure-accuracy samples."""
import copy
from datetime import datetime, timezone

import pytest

from src.portwatch_os.intelligence import voyage_exposure as e

NOW=datetime(2026,10,16,10,tzinfo=timezone.utc)


def event(**changes):
    return {'noticeId':'NAVCEN_MSI:fixture-a','providerNoticeId':'fixture-a','areaId':'ASSET_A','title':'Synthetic bridge interval',
        'sourceFamily':'NAVCEN_MSI','sourceStatus':'CURRENT','status':'SCHEDULED','extractionStatus':'SUPPORTED',
        'calculationSupported':True,'availableAt':NOW.isoformat(),'checkedAt':NOW.isoformat(),
        'windows':[{'start':'2026-10-17T08:30:00Z','end':'2026-10-17T14:15:00Z','timeZone':'America/New_York'}],
        'coordinates':{'lat':34.21828,'lon':-77.81259},**changes}


def vessel(**changes):
    episode={'id':'call-a','namespace':'visitor-a','vesselId':'ship-a','portCode':'INNSA'}
    plan={'id':'plan-a','areaId':'ASSET_A','route':['ASSET_A','INNSA'],'passageAt':'2026-10-17T12:00:00Z',
        'openingRequired':True,'emergencyTransit':False,'timezoneAssumption':'America/New_York','operationalEpisode':episode,
        'characteristics':{'loaM':70,'beamM':12,'draughtM':3,'airDraughtM':9}}
    return {'id':'ship-a','name':'Synthetic voyage','portCode':'INNSA','laneCode':'EUR_IND','lat':34.21828,'lon':-77.81259,
        'operationalEpisode':episode,'declaredPassage':plan,**changes}


def test_explicit_asset_and_time_support_declared_exposure_only():
    row=e.match(event(),vessel(),NOW)
    assert row['status']==e.CONFIRMED and row['calculable']
    assert row['timingOverlap']['end']=='2026-10-17T14:15:00Z'
    assert not row['declaredExposureIsObserved']
    # Same destination, broad lane and even the identical schematic position prove nothing.
    unproven=e.match(event(),vessel(declaredPassage=None),NOW)
    assert unproven['status']==e.NONE and not unproven['calculable']
    candidate=e.match(event(),vessel(declaredPassage=None,possibleAssetIds=['ASSET_A']),NOW)
    assert candidate['status']==e.POSSIBLE and 'explicitPassageConfirmation' in candidate['missingInputs']


def test_known_expiry_is_separate_from_failed_source_check():
    expired=event(sourceStatus='UNAVAILABLE',productThrough='2026-10-15T23:59:59Z')
    row=e.match(expired,vessel(),NOW)
    assert row['sourceStatus']=='UNAVAILABLE' and row['sourceValidity']=='EXPIRED'
    assert not row['calculable']
    cancelled=e.match(event(sourceStatus='UNAVAILABLE',status='CANCELLED'),vessel(),NOW)
    assert cancelled['sourceStatus']=='UNAVAILABLE' and cancelled['sourceValidity']=='CANCELLED'
    assert not cancelled['calculable']


def test_route_geometry_proximity_remains_possible_and_schematic_geometry_is_excluded():
    geometry={'type':'LineString','basis':'OPERATOR_DECLARED_ROUTE','coordinates':[[-77.813,34.21],[-77.812,34.23]]}
    assert e.match(event(),vessel(declaredPassage=None,routeGeometry=geometry),NOW)['status']==e.POSSIBLE
    geometry['basis']='SCHEMATIC_VISUALIZATION'
    assert e.match(event(),vessel(declaredPassage=None,routeGeometry=geometry),NOW)['status']==e.NONE
    assert e.match(event(areaId=None),vessel(),NOW)['status']==e.INSUFFICIENT


@pytest.mark.parametrize('changes',[
    {'sourceStatus':'MISSING'},{'sourceStatus':'UNAVAILABLE'},{'status':'CANCELLED'},
    {'status':'EXPIRED'},{'extractionStatus':'UNSUPPORTED','calculationSupported':False},
    {'availableAt':'2026-10-18T00:00:00Z'}, {'checkedAt':'2026-10-15T00:00:00Z'}])
def test_invalid_source_remains_inspectable_but_cannot_calculate(changes):
    row=e.match(event(**changes),vessel(),NOW)
    assert row['status']==e.CONFIRMED and not row['calculable']


@pytest.mark.parametrize('changes,expected',[
    ({'passageAt':'2026-10-17T14:15:00Z'},e.NONE),
    ({'passageAt':None},e.INSUFFICIENT),
    ({'operationalEpisode':{'id':'another-call'}},e.INSUFFICIENT),
    ({'route':['INNSA']},e.INSUFFICIENT)])
def test_temporal_membership_and_call_identity_are_not_guessed(changes,expected):
    ship=vessel();ship['declaredPassage'].update(changes)
    row=e.match(event(),ship,NOW)
    assert row['status']==expected and not row['calculable']


@pytest.mark.parametrize('changes',[{'openingRequired':False},{'emergencyTransit':True},
    {'characteristics':{}},{'timezoneAssumption':'UTC'}])
def test_exemptions_and_missing_declarations_never_produce_quantified_options(changes):
    ship=vessel();ship['declaredPassage'].update(changes)
    assert not e.match(event(),ship,NOW)['calculable']


def test_queue_is_bidirectional_deterministic_and_heuristic_not_probability():
    events=[event(),event(noticeId='NAVCEN_MSI:fixture-b',providerNoticeId='fixture-b',areaId='ASSET_B',status='EXPIRED')]
    ships=[vessel(),vessel(id='ship-b',name='Unconfirmed',declaredPassage=None,possibleAssetIds=['ASSET_A'])]
    rows=e.queue(events,ships,NOW)
    assert rows==e.queue(list(reversed(events)),list(reversed(ships)),NOW)
    assert rows[0]['status']==e.CONFIRMED and rows[0]['priority']['rank']==1
    assert 'not disruption probability' in rows[0]['priority']['label']
    assert len(e.queue(events,ships,NOW,event_id='fixture-a'))==2
    assert len(e.queue(events,ships,NOW,vessel_id='ship-a'))==2
    assert all(row['priority']['score']==0 for row in rows if row['sourceValidity']=='EXPIRED')
