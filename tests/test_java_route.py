from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
import pytest

@pytest.fixture
def app(tmp_path):
    from backend.main import create_app
    return create_app(tmp_path, demo=True)


def test_java_progress_and_daily_quota(app, monkeypatch):
    from backend.agent import ModelConfig
    import backend.java_route as module
    app.state.model_config = ModelConfig('dummy', 'https://example.test/v1', 'dummy')
    monkeypatch.setattr(module, 'run_agent', lambda *a, **k: {'status':'ok','mode':'ai','message':'完成','usage':{}})
    with TestClient(app) as c:
        assert c.get('/api/java-route').status_code == 401
        assert c.post('/api/auth/login',json={'username':'student','password':'Study2026!'}).status_code == 200
        route=c.get('/api/java-route').json()
        assert len(route['topics']) == 9
        assert c.post('/api/java-route/progress',json={'resource_id':'java-basic','completed':True}).status_code == 200
        for _ in range(10):
            assert c.post('/api/java-route/ask',json={'question':'什么是类？'}).status_code == 200
        assert c.post('/api/java-route/ask',json={'question':'还有问题'}).status_code == 429
        assert c.post('/api/learning/chat/retail',json={'question':'旧答疑'}).status_code == 429
        assert c.post('/api/auth/login',json={'username':'student2','password':'Study2026!'}).status_code == 200
        assert c.get('/api/java-route').json()['completed'] == []
        assert c.get('/api/java-route').json()['remaining'] == 10
        assert c.post('/api/auth/login',json={'username':'student','password':'Study2026!'}).status_code == 200
        assert 'java-basic' in c.get('/api/java-route').json()['completed']

def test_quota_resets_and_failure_is_recorded(app, monkeypatch):
    from backend.agent import ModelConfig
    import backend.java_route as module
    day=['2026-11-05']
    monkeypatch.setattr(module, 'china_day', lambda:day[0])
    monkeypatch.setattr(module, 'run_agent', lambda *a, **k: {'status':'error','mode':'ai','message':'模型未响应','usage':{'input_tokens':12}})
    app.state.model_config=ModelConfig('dummy','https://example.test/v1','dummy')
    with TestClient(app) as c:
        c.post('/api/auth/login',json={'username':'student','password':'Study2026!'})
        result=c.post('/api/java-route/ask',json={'question':'什么是类？'}).json()
        assert result['status']=='error' and result['remaining']==9
        with app.state.store.connect() as db:
            assert 'input_tokens' in db.execute('SELECT result FROM java_ai_log').fetchone()['result']
        day[0]='2026-11-06'
        assert c.get('/api/java-route').json()['remaining']==10
        c.post('/api/java-route/progress',json={'resource_id':'java-basic','completed':True})
        c.post('/api/java-route/progress',json={'resource_id':'java-basic','completed':False})
        assert not c.get('/api/java-route').json()['completed']

def test_quota_concurrent_requests_never_exceed_limit(app, monkeypatch):
    from backend.agent import ModelConfig
    import backend.java_route as module
    monkeypatch.setattr(module, 'run_agent', lambda *a, **k: {'status':'ok','mode':'ai','message':'完成'})
    app.state.model_config=ModelConfig('dummy','https://example.test/v1','dummy')
    with TestClient(app) as c:
        c.post('/api/auth/login',json={'username':'student','password':'Study2026!'})
        with ThreadPoolExecutor(max_workers=12) as pool:
            statuses=list(pool.map(lambda _:c.post('/api/java-route/ask',json={'question':'什么是类'}).status_code,range(14)))
        assert statuses.count(200)==10 and statuses.count(429)==4
