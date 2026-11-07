from fastapi.testclient import TestClient
from backend.main import create_app
from backend.course import dataset
from backend.grading import reference


def prepared(client):
    assert client.post('/api/auth/login',json={'username':'student','password':'Study2026!'}).status_code==200
    assert client.post('/api/diagnostic',json={'answers':[1,0,2,1,2,0]}).status_code==200
    assert client.post('/api/submit/clean',files={'file':('clean.csv',dataset('A',False),'text/csv')}).json()['grades']['clean']['score']==20
    assert client.post('/api/submit/metrics',json={'values':reference()['metrics']}).json()['grades']['metrics']['score']==25
    assert client.post('/api/submit/groups',json={'tables':reference()['groups']}).json()['grades']['groups']['score']==15
    state=client.get('/api/state').json();eid=next(k for k in state['evidence'] if k.startswith('metric:'))
    report={'observations':[{'text':'净销售额需要考虑退款。','evidence_id':eid}],'recommendations':[{'text':'检查渠道退款情况','evidence_id':eid,'validation':'比较后续同长度窗口的退款率'},{'text':'访谈客户确认原因','evidence_id':eid,'validation':'记录访谈及商品退货原因'}],'limitations':'<script>alert(1)</script> 本数据不含成本，不能推断利润。'}
    assert client.post('/api/report',json=report).status_code==200
    return report


def test_full_training_delivers_real_portfolio_without_ai_score(tmp_path):
    app=create_app(tmp_path,demo=True)
    with TestClient(app) as c:
        prepared(c)
        assert c.post('/api/defense/start').status_code==200
        for answer in ('净销售额要扣除退款。','建议先检查渠道退款，设置四周验证期。','不能证明因果，也缺少成本。'):
            assert c.post('/api/defense/answer',json={'answer':answer}).status_code==200
        assert c.post('/api/transfer',json={'values':reference('B')['metrics'],'answers':[2,1,0,2,0,1]}).status_code==200
        state=c.get('/api/state').json()
        assert state['progress']['finished'] is True
        assert state['report_review'] is None
        assert state['transfer']['posttest']['score']==6
        html=c.get('/api/export/html').text
        assert '<script>alert(1)</script>' not in html
        assert '&lt;script&gt;' in html
        assert 'AI_API_KEY' not in html
        assert c.post('/api/transfer',json={'values':reference('B')['metrics'],'answers':[2,1,0,2,0,1]}).status_code==409


def test_actual_upstream_resubmission_invalidates_report_and_defense(tmp_path):
    with TestClient(create_app(tmp_path,demo=True)) as c:
        prepared(c);c.post('/api/defense/start')
        state=c.post('/api/submit/metrics',json={'values':reference()['metrics']}).json()
        assert state['report_stale']
        assert state['defense']==[]
        assert state['grades']['groups'] is None
        assert c.post('/api/defense/start').status_code==409


def test_learner_state_survives_application_restart(tmp_path):
    with TestClient(create_app(tmp_path,demo=True)) as c:
        prepared(c)
    with TestClient(create_app(tmp_path,demo=True)) as c:
        c.post('/api/auth/login',json={'username':'student','password':'Study2026!'})
        assert c.get('/api/state').json()['objective_score']==60
