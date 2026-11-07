"""Real API-backed student questions, isolated by project, enrollment and version."""
import copy
import secrets
import time
from fastapi import Depends, HTTPException
from .agent import run_agent
from . import engineering_course as engineering
from .engineering_agent import context_for as engineering_context
from . import learning
from .java_route import reserve_ai_quota

FAQ={'environment':'请解释这门训练如何下载源码、在本地启动和上传ZIP，不讨论候补实现。','concept':'请解释HTTP状态码、认证与授权的基础区别，用与活动报名无关的小例子，不解答当前独立任务。'}

def mount_chat(app,store,student,retail_context):
    def load(uid,pid):return store.load_project(uid,pid,engineering.initial_state)
    @app.get('/api/learning/chat/{pid}')
    def history(pid:str,current=Depends(student)):
        if pid not in ('retail',engineering.PROJECT):raise HTTPException(404,'项目不存在。')
        return {'threads':load(current['id'],pid).get('chats',[])}

    @app.post('/api/learning/chat/{pid}')
    def ask(pid:str,payload:dict,current=Depends(student)):
        if pid not in ('retail',engineering.PROJECT):raise HTTPException(404,'项目不存在。')
        question=payload.get('question','');thread_id=payload.get('thread_id');kind=payload.get('kind','A')
        if not isinstance(question,str) or not 1<=len(question.strip())<=2000 or kind not in ('A','B'):raise HTTPException(422,'问题须为1—2000字。')
        with store.user_lock(current['id']):
            original=load(current['id'],pid);draft=copy.deepcopy(original)
            if pid==engineering.PROJECT and kind=='B' and not engineering.progress(draft)['completed'][5]:raise HTTPException(409,'需求B尚未解锁，请先完成A的工程报告、三题答辩和后测。')
            independent=pid==engineering.PROJECT and engineering.progress(draft)['stage']==6 and draft['b_mode']=='independent' and not draft['transfer']
            if pid=='retail' and learning.independent(pid,draft):raise HTTPException(409,'当前为独立测评，不能询问当前任务的解法。')
            if independent:
                faq=payload.get('faq_id')
                if faq not in FAQ:raise HTTPException(409,'当前为独立测评。可以选择环境/通用概念问题，或先点击“开启AI协作”后再询问当前任务解法。')
                question=FAQ[faq]
            context=engineering_context(draft,'question',kind) if pid==engineering.PROJECT else retail_context(draft,'question')
            if independent:context={'purpose':'question','project_id':pid,'facts':{'faq:public':{'text':'只提供环境启动与通用概念，不讨论当前独立任务解法。'}},'evidence_ids':['faq:public'],'policy':'禁止针对当前测评任务提供定位、实现或示例代码。'}
            threads=draft.setdefault('chats',[])
            thread=next((t for t in threads if t['id']==thread_id),None) if thread_id else None
            if thread_id and not thread:raise HTTPException(404,'对话不属于当前项目。')
            if not thread:
                if len(threads)>=50:raise HTTPException(409,'已有50段对话，请继续已有对话。')
                thread={'id':secrets.token_hex(8),'title':question[:35],'project_id':pid,'created':time.time(),'messages':[]};threads.append(thread)
            if len(thread['messages'])>=120:raise HTTPException(409,'本段对话已满，请新建对话。')
            submission=engineering.latest_submission(draft,kind) if pid==engineering.PROJECT else None
            version=submission['hash'] if submission else str(draft.get('data_revision',0))
            context.update(question=question,selected_issue='' if independent else str(payload.get('issue',''))[:1200],conversation=[] if independent else [{'role':m['role'],'text':m['text'][:1500],'version':m.get('version')} for m in thread['messages'][-8:]],current_version=version)
            quoted=[]
            def answer(args):
                text=args['text'];ids=args['evidence_ids']
                if not isinstance(text,str) or not 1<=len(text)<=4000 or not isinstance(ids,list) or any(i not in context['evidence_ids'] for i in ids):raise ValueError('答案引用无效')
                quoted.append({'text':text,'evidence_ids':ids});return {'saved':True,'version':version,'evidence_ids':ids}
            if app.state.model_config.enabled:
                reserve_ai_quota(store,current['id'])
            result=run_agent('question',context,app.state.model_config,{'answer_question':answer})
            result.update(id=secrets.token_hex(8),purpose='question',created=time.time(),actions_committed=result['status']=='ok' and result['mode']=='ai')
            # Record the real attempt, even when the provider is unavailable.
            target=draft if result['status']=='ok' else original
            target_threads=target.setdefault('chats',[])
            target_thread=next((t for t in target_threads if t['id']==thread['id']),None)
            if not target_thread:target_thread={**thread,'messages':[]};target_threads.append(target_thread)
            target_thread['messages'].extend([{'id':secrets.token_hex(6),'role':'user','text':question,'version':version,'created':time.time()},{'id':result['id'],'role':'assistant','text':quoted[-1]['text'] if result['status']=='ok' and quoted else result['message'],'evidence_ids':quoted[-1]['evidence_ids'] if result['status']=='ok' and quoted else [],'version':version,'created':time.time(),'status':result['status'],'model':result['model'],'actions':result['actions']}])
            if result['mode']=='ai':target['agent_runs'].append(result)
            if result['status']=='ok' and result['mode']=='ai' and not independent:
                memory=store.load_learning(current['id'],pid);learning.mark_assisted(memory,learning.source_version(pid,target,kind),'本题进行期间使用了AI答疑，保守标为有协助。');store.save_learning(current['id'],pid,memory)
            store.save_project(current['id'],pid,target)
            return {'thread':target_thread,'run':result}
