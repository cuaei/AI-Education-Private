import copy
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.agent import ModelConfig, run_agent
from backend.main import create_app, tools_for
from backend.course import dataset
from backend.grading import analyze_csv, compare_groups, reference
from backend.storage import initial_state
from backend.portfolio import export_markdown
from test_journey import prepared


def test_extra_csv_columns_rejected():
    lines=dataset('A',False).decode('utf-8-sig').splitlines()
    malformed='\n'.join([lines[0]]+['unexpected,'+r for r in lines[1:]])
    with pytest.raises(ValueError):analyze_csv(malformed.encode())


@pytest.mark.parametrize('extra',[[{'name':'fake','current':999999}],None])
def test_extra_dimensions_rejected(extra):
    tables=copy.deepcopy(reference()['groups']);tables['invented']=extra
    with pytest.raises(ValueError):compare_groups(tables)


def test_timeout_cost_is_unknown_even_with_configured_prices():
    def server(request):raise httpx.ReadTimeout('timeout',request=request)
    result=run_agent('feedback',{},ModelConfig('k','https://p.example/v1','m',1,2),{},httpx.MockTransport(server))
    assert result['usage']['input_tokens'] is None
    assert result['cost'] is None


def test_nested_invalid_tool_output_cannot_crash_or_score_metadata():
    state=initial_state();state['report']={'id':'generated-id','observations':[{'text':'学生真实观察'}],'recommendations':[],'limitations':'学生限制'}
    tools=tools_for(state,'report')
    names=['观察与假设区分','证据','建议可执行性','验证方法','限制说明']
    for quote in ('generated-id','学生真实观察'):
        rows=[{'criterion':n,'score':5,'reason':'依据','quote':quote,'evidence_id':'report:generated-id'} for n in names]
        if quote=='generated-id':
            with pytest.raises(ValueError):tools['review_report']({'criteria':rows})
        else:assert tools['review_report']({'criteria':rows})['score']==25
    def server(request):
        return httpx.Response(200,json={'choices':[{'message':{'tool_calls':[{'id':'c','function':{'name':'review_report','arguments':json.dumps({'criteria':[0]*5})}}]}}]})
    result=run_agent('report',{'evidence_ids':['report:generated-id']},ModelConfig('k','https://p.example/v1','m'),tools,httpx.MockTransport(server))
    assert result['needs_human_review']
    assert all(not a['executed'] for a in result['actions'])


def test_idempotent_submission_preserves_downstream_and_rejects_changed_payload(tmp_path):
    app=create_app(tmp_path,demo=True)
    with TestClient(app) as c:
        prepared(c)
        payload={'values':reference()['metrics']};headers={'Idempotency-Key':'stable-operation'}
        first=c.post('/api/submit/metrics',json=payload,headers=headers)
        c.post('/api/submit/groups',json={'tables':reference()['groups']})
        before=c.get('/api/state').json()
        assert c.post('/api/submit/metrics',json=payload,headers=headers).json()==first.json()
        after=c.get('/api/state').json()
        assert after['revision']==before['revision'] and after['grades']['groups']['passed']
        changed=copy.deepcopy(payload);changed['values']['aov']=1
        assert c.post('/api/submit/metrics',json=changed,headers=headers).status_code==409


def test_stale_report_excluded_and_report_history_preserved(tmp_path):
    with TestClient(create_app(tmp_path,demo=True)) as c:
        report=prepared(c);old=c.get('/api/state').json()['report']['id']
        report['limitations']='updated student text'
        c.post('/api/report',json=report)
        state=c.get('/api/state').json()
        assert any(h['report']['id']==old for h in state['work_history'])
        c.post('/api/submit/metrics',json={'values':reference()['metrics']})
        assert 'updated student text' not in c.get('/api/export/md').text
        assert c.get('/api/portfolio').json()['report'] is None


def test_founder_can_inspect_work_but_cannot_score_absent_work(tmp_path):
    app=create_app(tmp_path,demo=True)
    with TestClient(app) as c:
        prepared(c);uid=c.get('/api/me').json()['id']
        assert c.get('/api/operator/learners/'+uid).status_code==403
        c.post('/api/auth/login',json={'username':'founder','password':'Founder2026!'})
        detail=c.get('/api/operator/learners/'+uid).json()
        assert detail['report']['observations'][0]['text']=='净销售额需要考虑退款。'
        assert 'password' not in detail['user']
        assert c.post('/api/operator/review',json={'user_id':uid,'note':'复核','defense_review':15}).status_code==409
        founder=app.state.store.find_user('founder');state=app.state.store.load(founder['id'])
        state['agent_runs'].append({'cost':1.2});app.state.store.save(founder['id'],state)
        assert c.get('/api/operator').json()['summary']['known_cost']==1.2
