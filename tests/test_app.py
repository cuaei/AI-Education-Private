import importlib
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app(tmp_path):
    assert importlib.util.find_spec('backend.main'), 'missing application implementation'
    return importlib.import_module('backend.main').create_app(tmp_path, demo=True)


def login(client, name='student'):
    password = 'Founder2026!' if name == 'founder' else 'Study2026!'
    result = client.post('/api/auth/login', json={'username':name,'password':password})
    assert result.status_code == 200


def test_authentication_required_and_wrong_password_rejected(app):
    with TestClient(app) as c:
        assert c.get('/api/state').status_code == 401
        assert c.post('/api/auth/login', json={'username':'student','password':'wrong'}).status_code == 401
        login(c)
        assert c.get('/api/state').json()['user']['username'] == 'student'


def test_diagnostic_persisted_across_clients_and_student_isolation(app):
    with TestClient(app) as c:
        login(c)
        assert c.post('/api/diagnostic', json={'answers':[1,0,2,1,2,0]}).status_code == 200
        assert c.get('/api/state').json()['diagnostic']['score'] == 6
        login(c,'student2')
        assert c.get('/api/state').json()['diagnostic'] is None
        assert c.get('/api/operator').status_code == 403
        login(c)
        assert c.get('/api/state').json()['diagnostic']['score'] == 6


def test_missing_prerequisites_cannot_be_bypassed(app):
    with TestClient(app) as c:
        login(c)
        assert c.post('/api/report', json={'observations':[], 'recommendations':[], 'limitations':'none'}).status_code == 409
        assert c.post('/api/coach', json={'purpose':'defense'}).status_code == 409


def test_no_key_is_honest_basic_mode(app):
    with TestClient(app) as c:
        login(c)
        r=c.post('/api/coach',json={'purpose':'diagnosis'})
        assert r.status_code == 200
        assert r.json()['mode'] == 'basic'
        assert c.get('/api/state').json()['agent_runs'] == []


def test_oversized_file_and_invalid_metric_input_rejected(app):
    with TestClient(app) as c:
        login(c)
        c.post('/api/diagnostic',json={'answers':[1,0,2,1,2,0]})
        assert c.post('/api/submit/clean',files={'file':('test.csv',b'x'*(2*1024*1024+1),'text/csv')}).status_code == 422
        assert c.post('/api/submit/metrics',json={'values':{'current_net':'nan'}}).status_code in (409,422)


def test_logout_invalidates_session_and_other_origins_cannot_mutate(app):
    with TestClient(app) as c:
        login(c)
        assert c.post('/api/diagnostic',json={'answers':[1]*6},headers={'Origin':'https://evil.example'}).status_code == 403
        assert c.post('/api/auth/logout').status_code == 200
        assert c.get('/api/state').status_code == 401


def test_delete_student_data_and_public_share_revocation(app):
    with TestClient(app) as c:
        login(c)
        r=c.post('/api/share')
        assert r.status_code == 200
        token=r.json()['token']
        assert c.get('/api/shared/'+token).status_code == 200
        assert c.delete('/api/share').status_code == 200
        assert c.get('/api/shared/'+token).status_code == 404
        assert c.delete('/api/account').status_code == 200
        assert c.get('/api/state').status_code == 401


def test_upstream_changes_make_old_report_stale(app):
    # Application state is set through the same durable store used by submissions.
    with TestClient(app) as c:
        login(c)
        store=app.state.store
        user=store.find_user('student')
        state=store.load(user['id'])
        state['report']={'id':'test-report','data_revision':0,'observations':[], 'recommendations':[], 'limitations':'test'}
        state['report_stale']=False
        store.save(user['id'],state)
        c.post('/api/diagnostic',json={'answers':[1,0,2,1,2,0]})
        assert c.get('/api/state').json()['report_stale'] is True
