from fastapi.testclient import TestClient

from backend.app.auth_store import AuthStore, get_auth_store
from backend.app.main import app
from src.portwatch_os.advisories.store import AdvisoryStore
from src.portwatch_os.decision.engine import DecisionEngine
from src.portwatch_os.decision.model import DecisionActor
from tests.test_advisories import advisory, controller
from tests.test_robust_decisions import keep, problem_with


def test_company_approval_and_private_decision_require_server_scope(tmp_path, monkeypatch):
    store = AuthStore(tmp_path / 'identity.db')
    engine = DecisionEngine()
    problem = problem_with([keep()])
    problem.actor = DecisionActor('SHIPPING_COMPANY', organisation='QA carrier')
    problem.world_revision = {}
    marker = 'QA_FICTIONAL_COMPANY_PRIVATE'
    problem.evidence['qaPrivateMarker'] = marker
    engine._store(problem)
    monkeypatch.setenv('PORTWATCH_IDENTITY_MODE', 'verified')
    monkeypatch.setattr('backend.app.auth_store.get_auth_store', lambda: store)
    monkeypatch.setattr('backend.app.routes.decisions.get_engine', lambda: engine)
    monkeypatch.setitem(app.dependency_overrides, get_auth_store, lambda: store)

    password = 'fixture-disposable-9988'
    path = '/api/decisions/problems/' + problem.decision_id
    headers = {}
    client = TestClient(app)
    for name, role, vessels, organisation, approve in (
        ('owner', 'SHIPPING_COMPANY', (), 'QA carrier', True),
        ('viewer', 'SHIPPING_COMPANY', (), 'QA carrier', False),
        ('rival', 'SHIPPING_COMPANY', (), 'Other carrier', True),
        ('assigned', 'VESSEL_OPERATOR', ('V-1',), 'QA carrier', True),
        ('sibling', 'VESSEL_OPERATOR', ('V-2',), 'QA carrier', True),
    ):
        profile = store.provision(name + '@example.invalid', password, role=role, display_name=name,
                                  vessel_ids=vessels, organisation=organisation, can_approve=approve)
        login = client.post('/api/auth/login', json={'email': profile['email'], 'password': password})
        assert login.status_code == 200
        headers[name] = {'Authorization': 'Bearer ' + login.json()['accessToken'],
                         'X-PortWatch-Role': 'NATIONAL_ADMIN', 'X-PortWatch-Actor': 'forged'}
        if name == 'owner':
            owner_id = profile['id']
    assert client.get(path).status_code == 401
    assert marker in client.get(path, headers=headers['viewer']).text
    assert client.post(path + '/transition', headers=headers['owner'], json={'target': 'REVIEWED'}).status_code == 200
    approval = {'target': 'APPROVED', 'optionId': 'keep_plan'}
    for name in ('rival', 'assigned', 'sibling'):
        response = client.get(path, headers=headers[name])
        assert response.status_code == 403 and marker not in response.text
        assert marker not in client.get('/api/decisions/problems', headers=headers[name]).text
        assert client.post(path + '/transition', headers=headers[name], json=approval).status_code == 403
    assert client.post(path + '/transition', headers=headers['viewer'], json=approval).status_code == 403
    assert problem.workflow == 'REVIEWED' and problem.human_choice is None
    assert client.post(path + '/transition', headers=headers['owner'], json=approval).status_code == 200
    assert problem.human_choice == 'keep_plan' and problem.workflow_history[-1]['actor'] == owner_id

    advisories = AdvisoryStore(':memory:')
    monkeypatch.setattr('backend.app.routes.advisories.get_advisory_store', lambda: advisories)
    row = advisory(recipient_vessel_id='V-1', recipient_organisation='QA carrier',
                   evidence={'insurance': {'contract': marker}},
                   recommendation={'recommendedArrival': '2026-11-04T09:00:00Z', 'rates': [marker]})
    advisories.create(row, principal=controller())
    advisories.act(row.advisory_id, 'under_review', principal=controller())
    advisories.act(row.advisory_id, 'issued', principal=controller())
    advisory_path = '/api/advisories/' + row.advisory_id
    assert client.get(advisory_path, headers=headers['sibling']).status_code == 404
    assert client.post(advisory_path + '/transition', headers=headers['sibling'],
                       json={'target': 'acknowledged'}).status_code == 403
    assert advisories.require(row.advisory_id).state == 'issued'
    response = client.get(advisory_path, headers=headers['assigned'])
    assert response.status_code == 200 and marker not in response.text
    assert response.json()['recommendation'] == {'recommendedArrival': '2026-11-04T09:00:00Z'}
    assert marker not in client.get('/api/advisories', headers=headers['assigned']).text
    client.close()
