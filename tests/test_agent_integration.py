import json
import copy
import httpx
from fastapi.testclient import TestClient
from backend.agent import ModelConfig, run_agent
from backend.main import create_app
from test_journey import prepared


def test_three_tool_rounds_have_a_final_response_and_count_all_usage():
    count=0
    def server(request):
        nonlocal count
        count+=1;body=json.loads(request.content)
        if count<=3:msg={'tool_calls':[{'id':str(count),'function':{'name':'check_metrics','arguments':'{}'}}]}
        else:
            assert 'tools' not in body
            msg={'content':json.dumps({'message':'请核对计算口径','evidence_ids':['e1'],'needs_human_review':False})}
        return httpx.Response(200,json={'choices':[{'message':msg}],'usage':{'prompt_tokens':10,'completion_tokens':2}})
    result=run_agent('feedback',{'evidence_ids':['e1']},ModelConfig('key','https://p.example/v1','m',1,2),{'check_metrics':lambda args:{'evaluation':'actual'}},httpx.MockTransport(server))
    assert result['status']=='ok' and count==4
    assert result['usage']=={'input_tokens':40,'output_tokens':8}


def test_real_application_tool_side_effects_are_committed_and_retries_replayed(tmp_path,monkeypatch):
    def server(request):
        body=json.loads(request.content)
        if body['messages'][-1]['role']=='tool':
            result=json.loads(body['messages'][-1]['content']);assert result['exercise']['skill_id']=='refund'
            msg={'content':json.dumps({'message':'先完成退款补练。','evidence_ids':[],'needs_human_review':False})}
        else:msg={'tool_calls':[{'id':'assign','function':{'name':'assign_remediation','arguments':json.dumps({'skill_id':'refund','hint_level':1})}}]}
        return httpx.Response(200,json={'choices':[{'message':msg}],'usage':{'prompt_tokens':8,'completion_tokens':4}})
    transport=httpx.MockTransport(server)
    monkeypatch.setattr('backend.main.run_agent',lambda purpose,context,config,tools:run_agent(purpose,context,config,tools,transport))
    app=create_app(tmp_path,demo=True);app.state.model_config=ModelConfig('test-key','https://p.example/v1','m')
    with TestClient(app) as c:
        c.post('/api/auth/login',json={'username':'student','password':'Study2026!'})
        headers={'Idempotency-Key':'coach-once'}
        first=c.post('/api/coach',json={'purpose':'feedback'},headers=headers).json()
        assert first['actions_committed']
        assert c.post('/api/coach',json={'purpose':'feedback'},headers=headers).json()==first
        state=c.get('/api/state').json()
        assert len(state['remediation'])==1 and len(state['agent_runs'])==1
        assert 'test-key' not in json.dumps(state)


def test_invalid_final_rolls_back_staged_exercise_but_retains_paid_attempt(tmp_path,monkeypatch):
    def server(request):
        body=json.loads(request.content)
        if body['messages'][-1]['role']=='tool':msg={'content':'not-json'}
        else:msg={'tool_calls':[{'id':'a','function':{'name':'assign_remediation','arguments':'{"skill_id":"refund","hint_level":1}'}}]}
        return httpx.Response(200,json={'choices':[{'message':msg}],'usage':{'prompt_tokens':8,'completion_tokens':4}})
    monkeypatch.setattr('backend.main.run_agent',lambda p,c,cfg,t:run_agent(p,c,cfg,t,httpx.MockTransport(server)))
    app=create_app(tmp_path,demo=True);app.state.model_config=ModelConfig('key','https://p.example/v1','m')
    with TestClient(app) as c:
        c.post('/api/auth/login',json={'username':'student','password':'Study2026!'})
        result=c.post('/api/coach',json={'purpose':'feedback'}).json()
        assert result['status']=='invalid_output' and not result['actions_committed']
        state=c.get('/api/state').json()
        assert not state['remediation'] and len(state['agent_runs'])==1 and state['human_reviews']


def test_public_share_is_opt_in_and_snapshotted(tmp_path):
    with TestClient(create_app(tmp_path,demo=True)) as c:
        prepared(c);c.post('/api/defense/start');c.post('/api/defense/answer',json={'answer':'private answer'})
        default=c.post('/api/share',json={}).json()['token']
        assert 'private answer' not in c.get('/api/shared/'+default).text
        selected=c.post('/api/share',json={'include_defense':True}).json()['token']
        assert c.get('/api/shared/'+selected).json()['defense_excerpt'][0]['answer']=='private answer'
        assert c.delete('/api/share').status_code==200
        assert c.get('/api/shared/'+selected).status_code==404
