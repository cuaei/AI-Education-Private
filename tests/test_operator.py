import importlib
from fastapi.testclient import TestClient


def test_operator_only_can_create_accounts_and_record_service_time(tmp_path):
    assert importlib.util.find_spec('backend.main'), 'missing operator implementation'
    app=importlib.import_module('backend.main').create_app(tmp_path,demo=True)
    with TestClient(app) as c:
        c.post('/api/auth/login',json={'username':'student','password':'Study2026!'})
        assert c.post('/api/operator/users',json={'username':'learner','password':'SomePass123!'}).status_code==403
        c.post('/api/auth/login',json={'username':'founder','password':'Founder2026!'})
        assert c.post('/api/operator/users',json={'username':'learner','password':'SomePass123!'}).status_code==200
        learner=[x for x in c.get('/api/operator').json()['learners'] if x['username']=='learner'][0]
        assert c.post('/api/operator/review',json={'user_id':learner['id'],'minutes':12,'note':'检查解释依据'}).status_code==200
        assert c.get('/api/operator').json()['summary']['human_minutes']==12
        assert c.get('/api/operator').json()['summary']['real_participants']==1
