import importlib
import json
import httpx


def agent():
    assert importlib.util.find_spec('backend.agent'), 'missing model agent implementation'
    return importlib.import_module('backend.agent')


def test_model_selects_tool_and_receives_real_tool_result():
    def server(request):
        data=json.loads(request.content)
        assert 'thinking' not in data
        if data['messages'][-1]['role']=='tool':
            assert json.loads(data['messages'][-1]['content'])['result']==45
            msg={'content':json.dumps({'message':'扣除退款后再提交。','evidence_ids':['metrics:1'],'needs_human_review':False})}
        else:
            msg={'content':None,'tool_calls':[{'id':'call_1','type':'function','function':{'name':'check_metrics','arguments':'{}'}}]}
        return httpx.Response(200,json={'id':'r1','choices':[{'index':0,'message':msg,'finish_reason':'stop'}],'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}})
    mod=agent()
    cfg=mod.ModelConfig('secret','https://provider.example/v1','test-model')
    result=mod.run_agent('feedback',{'evidence_ids':['metrics:1']},cfg,{'check_metrics':lambda args:{'result':45}},transport=httpx.MockTransport(server))
    assert result['message']=='扣除退款后再提交。'
    assert result['usage']['input_tokens']==200
    assert result['actions'][0]['tool']=='check_metrics'
    assert 'secret' not in json.dumps(result)


def test_unknown_tool_cannot_mutate_state():
    def server(request):
        return httpx.Response(200,json={'choices':[{'message':{'content':None,'tool_calls':[{'id':'bad','type':'function','function':{'name':'delete_everything','arguments':'{}'}}]}}],'usage':{'prompt_tokens':1,'completion_tokens':1}})
    mod=agent()
    result=mod.run_agent('feedback',{'evidence_ids':[]},mod.ModelConfig('key','https://p.example/v1','m'),{},transport=httpx.MockTransport(server))
    assert result['needs_human_review']
    assert all(a.get('executed') is False for a in result['actions'])


def test_invented_evidence_is_not_accepted():
    def server(request):
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'message':'分析正确','evidence_ids':['someone-else'],'needs_human_review':False})}}]})
    mod=agent()
    result=mod.run_agent('report',{'evidence_ids':['report:1']},mod.ModelConfig('key','https://p.example/v1','m'),{},transport=httpx.MockTransport(server))
    assert result['needs_human_review']
    assert result['status']=='invalid_output'


def test_timeout_retries_once_and_does_not_leak_credentials():
    count=0
    def server(request):
        nonlocal count
        count+=1
        raise httpx.ReadTimeout('secret key internal details',request=request)
    mod=agent()
    result=mod.run_agent('feedback',{},mod.ModelConfig('secret','https://p.example/v1','m'),{},transport=httpx.MockTransport(server))
    assert count==2
    assert result['status']=='unavailable'
    assert 'secret' not in result['message']


def test_no_key_never_calls_http():
    mod=agent()
    result=mod.run_agent('feedback',{},mod.ModelConfig('','',''),{})
    assert result['mode']=='basic'
    assert result['usage']['input_tokens'] is None


def test_unreadable_provider_response_does_not_claim_free_request():
    mod=agent()
    result=mod.run_agent('feedback',{},mod.ModelConfig('key','https://p.example/v1','m',1,2),{},transport=httpx.MockTransport(lambda request:httpx.Response(200,text='invalid-json')))
    assert result['status']=='invalid_output'
    assert result['cost'] is None


def test_deepseek_explicitly_disables_thinking_and_completes_tool_loop():
    count=0
    def server(request):
        nonlocal count
        count+=1;body=json.loads(request.content)
        assert str(request.url)=='https://api.deepseek.com/chat/completions'
        assert body['model']=='deepseek-flash'
        assert body['thinking']=={'type':'disabled'}
        if body['messages'][-1]['role']=='tool':
            assert json.loads(body['messages'][-1]['content'])=={'verified':True}
            msg={'content':json.dumps({'message':'核验记录已读取。','evidence_ids':[],'needs_human_review':False})}
        else:msg={'tool_calls':[{'id':'c1','type':'function','function':{'name':'check_metrics','arguments':'{}'}}]}
        return httpx.Response(200,json={'choices':[{'message':msg}],'usage':{'prompt_tokens':10,'completion_tokens':5}})
    mod=agent()
    result=mod.run_agent('feedback',{},mod.ModelConfig('test-key','https://api.deepseek.com','deepseek-flash'),{'check_metrics':lambda args:{'verified':True}},httpx.MockTransport(server))
    assert count==2 and result['status']=='ok' and result['actions'][0]['executed']
