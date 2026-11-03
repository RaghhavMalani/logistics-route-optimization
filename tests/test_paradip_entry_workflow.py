import hashlib

from src.portwatch_os.intelligence import paradip_entry as pilot
from tests.test_current_recovery import step
from tests.test_demo_terminal import resources, setup


BASE = '/api/demo/terminal'
PATH = BASE + '/intelligence/paradip-entry-comparison'


def test_paradip_referral_keeps_unknowns_and_frozen_evidence(tmp_path, monkeypatch):
    original = b'software test bytes'
    monkeypatch.setattr(pilot, 'SHA', hashlib.sha256(original).hexdigest())
    monkeypatch.setattr(pilot, '_download', lambda url, limit: pilot.URL.encode() if url == pilot.CATALOGUE else original)
    store, client = setup(tmp_path, monkeypatch)
    token = store.create('SHIPPING_COMPANY')['accessToken']
    headers = {'Authorization': 'Bearer ' + token}
    assert client.post(PATH, headers=headers, json={'confirmed': True}).status_code == 422
    def declare_paradip(world):
        world['portCode'] = 'INPRT'
        world['fleet'][0]['portCode'] = 'INPRT'

    store.update(token, declare_paradip)
    assert client.post(PATH, headers=headers, json={'confirmed': False}).status_code == 422
    response = client.post(PATH, headers=headers, json={'confirmed': True})
    assert response.status_code == 200, response.text
    company = response.json()
    assert [option['status'] for option in company['options']] == ['REJECTED', 'FEASIBLE']
    basis = company['evidence']['intelligenceBasis']
    choice = company['options'][1]['optionId']
    decision_path = BASE + '/decisions/problems/' + company['decisionId']
    step(client, decision_path, headers, 'REVIEWED')
    step(client, decision_path, headers, 'APPROVED', choice)
    resources.cache_clear()
    store.switch(token, 'PORT_AUTHORITY')
    response = client.post(BASE + '/decisions/current-proposals/review', headers=headers, json={'decisionId': company['decisionId']})
    assert response.status_code == 200, response.text
    port_path = BASE + '/decisions/problems/' + response.json()['decisionId']
    step(client, port_path, headers, 'REVIEWED')
    step(client, port_path, headers, 'APPROVED', choice)
    response = client.post(port_path + '/handoff', headers=headers, json={})
    assert response.status_code == 200, response.text
    advisory = response.json()['advisories'][0]
    assert advisory['evidence']['intelligenceBasis'] == basis
    advisory_path = BASE + '/advisories/' + advisory['advisoryId']
    step(client, advisory_path, headers, 'under_review')
    step(client, advisory_path, headers, 'issued')
    store.switch(token, 'VESSEL_OPERATOR')
    step(client, advisory_path, headers, 'acknowledged')
    step(client, advisory_path, headers, 'accepted')
    store.switch(token, 'PORT_AUTHORITY')
    response = client.post(port_path + '/demo-outcome', headers=headers, json={})
    assert response.status_code == 200, response.text
    outcome = response.json()['outcome']
    assert outcome['kind'] == 'SIMULATED_DEMO_OUTCOME' and outcome['selectedAction'] == 'HOLD_AND_REFER'
    assert outcome['noticeRevisionId'] == pilot.SHA and outcome['eligibleForRealTarget'] is False
    assert outcome['actualEarliestPermittedAccess'] is outcome['totalScheduleShiftHours'] is outcome['selectedAssumedWaitHours'] is None
    other = store.create('SHIPPING_COMPANY')['accessToken']
    assert client.get(decision_path, headers={'Authorization': 'Bearer ' + other}).status_code == 404
    client.close()
