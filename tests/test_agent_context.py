from backend.main import context_for, tools_for
from backend.storage import initial_state
from backend import course

def test_agent_receives_exact_task_names_and_skill_ids_for_executable_plan():
    state=initial_state()
    state['diagnostic']=course.quiz_grade([0,0,2,1,2,0],'C')
    context=context_for(state,'diagnosis')
    assert '数据检查' in context['allowed_next_tasks']
    assert 'refund' in context['skill_catalog']
    assert 'answer' not in context['skill_catalog']['refund']
    result=tools_for(state,'diagnosis')['propose_next_task']({'task':context['allowed_next_tasks'][0],'reason':'完成前测后检查数据'})
    assert result['next_task']==state['next_task']

def test_operator_agent_knows_score_maximum_and_demo_accounts(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    from backend.agent import ModelConfig
    def agent(purpose,context,config,tools):
        facts=tools['operator_insights']({})
        assert facts['objective_max_score']==60
        assert all(l['is_demo'] for l in facts['learners'])
        assert all('username' not in l and 'password' not in l for l in facts['learners'])
        return {'mode':'basic','message':'汇总已核对'}
    monkeypatch.setattr('backend.main.run_agent',agent)
    app=create_app(tmp_path,demo=True);app.state.model_config=ModelConfig('key','https://p.example','m')
    with TestClient(app) as c:
        c.post('/api/auth/login',json={'username':'founder','password':'Founder2026!'})
        assert c.post('/api/operator/insights',json={}).status_code==200

def test_report_agent_cannot_claim_success_without_saving_review():
    import httpx,json
    from backend.agent import run_agent,ModelConfig
    transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'message':'报告已评分。','evidence_ids':[],'needs_human_review':False})}}],'usage':{'prompt_tokens':10,'completion_tokens':5}}))
    result=run_agent('report',{'evidence_ids':[]},ModelConfig('key','https://p.example','m'),{'review_report':lambda args:{}},transport)
    assert result['status']=='invalid_output'
    assert result['needs_human_review']

def test_deepseek_saves_primary_review_then_finishes_without_more_tools():
    import httpx,json
    from backend.agent import run_agent,ModelConfig
    saved=[]
    def provider(request):
        body=json.loads(request.content)
        if not saved:
            assert body['tool_choice']=={'type':'function','function':{'name':'review_report'}}
            message={'tool_calls':[{'id':'r','type':'function','function':{'name':'review_report','arguments':'{"criteria":[]}'}}]}
        else:
            assert body['tool_choice']=='none'
            assert body['response_format']=={'type':'json_object'}
            assert body['messages'][-1]['role']=='system'
            assert '答辩评价 criteria' not in body['messages'][0]['content']
            message={'content':json.dumps({'message':'评价已保存，请补充证据。','evidence_ids':[],'needs_human_review':False})}
        return httpx.Response(200,json={'choices':[{'message':message}],'usage':{'prompt_tokens':10,'completion_tokens':5}})
    def save(args):saved.append(args);return {'score':18}
    r=run_agent('report',{},ModelConfig('key','https://api.deepseek.com','deepseek-flash'),{'review_report':save},httpx.MockTransport(provider))
    assert r['status']=='ok' and len(saved)==1
