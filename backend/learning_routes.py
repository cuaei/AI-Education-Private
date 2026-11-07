"""Personalized teaching routes; exercise keys never cross the public boundary."""
import copy
import hashlib
import json
import secrets
import time
from fastapi import Depends,HTTPException
from . import learning as learn, engineering_course as engineering, learning_templates as templates
from .agent import run_agent

def mount_learning(app,store,student,founder,retail_context,engineering_context):
    def load(uid,pid):
        if pid not in templates.PROJECTS:raise HTTPException(404,'此项目尚未开放实训。')
        return store.load_project(uid,pid,engineering.initial_state)
    def access(pid,state,kind='A'):
        if kind not in ('A','B'):raise HTTPException(422,'提交类型不正确。')
        if not state['diagnostic']:raise HTTPException(409,'请先完成起点诊断。')
        if learn.independent(pid,state):raise HTTPException(409,'当前为独立测评，不能获取针对答案的变式或提示。工程课程可先明确开启AI协作。')
        if pid=='software-engineering' and kind=='B' and not engineering.progress(state)['completed'][5]:raise HTTPException(409,'需求B尚未解锁。')
    def reply(uid,pid,state,kind='A'):
        version=learn.source_version(pid,state,kind);memory=store.load_learning(uid,pid)
        return {**learn.public_learning(memory,version),'teacher_notes':app.state.classrooms.student_notes(uid,pid),'issues':learn.learning_evidence(pid,state,kind,memory),'catalog':templates.catalog(pid),'mode':'ai' if app.state.model_config.enabled else 'basic','independent':learn.independent(pid,state),'titles':{k:v['title'] for k,v in (learn.course.CARDS if pid=='retail' else engineering.CARDS).items()}}
    def checked_exercise(memory,pid,state,eid,kind):
        try:ex=learn.find_exercise(memory,eid)
        except KeyError:raise HTTPException(404,'练习不存在或不属于当前账号。')
        if ex['source_version']!=learn.source_version(pid,state,kind):raise HTTPException(409,'材料已更新，这道题已成为历史；请按当前版本安排新题。')
        return ex
    def save(uid,pid,memory):store.save_learning(uid,pid,memory)
    def plan_reply(uid,pid,state,kind,memory,run=None,cached=False,existing=None,prepared=None):
        version=learn.source_version(pid,state,kind)
        if existing:
            label='教师安排' if existing['source']=='teacher' else 'AI安排'
            outcome={'type':'existing','exercise_id':existing['id'],'message':f'已有一题尚未完成的{label}练习，已为你定位。请先作答，之后可以换一道新题；本次没有重复调用AI。'}
        elif run and run['status']!='ok':
            outcome={'type':'error','message':run['message']}
        elif run and any(a['tool']=='request_error_probe' and a['executed'] for a in run['actions']):
            outcome={'type':'probe','message':'AI需要先了解你的计算方法。请填写下方「说明实际步骤」；保存后会继续让AI安排练习。'}
        else:
            exercise=prepared or next((e for e in reversed(memory['exercises']) if e['source_version']==version and e['status']=='active'),None)
            outcome={'type':'exercise','message':'练习已准备好，请在下方作答。'}
            if exercise:outcome.update(exercise_id=exercise['id'])
        if cached:outcome['message']='已读取本次已有安排，没有重复调用AI。'+outcome['message']
        return {**reply(uid,pid,state,kind),'learning_outcome':outcome,**({'run':run} if run else {}),**({'cached':True} if cached else {})}

    @app.get('/api/projects/{pid}/learning')
    def get_learning(pid:str,kind:str='A',current=Depends(student)):
        if kind not in ('A','B'):raise HTTPException(422,'提交类型不正确。')
        with store.user_lock(current['id']):return reply(current['id'],pid,load(current['id'],pid),kind)

    @app.post('/api/projects/{pid}/learning/probes/{probe_id}')
    def probe(pid:str,probe_id:str,payload:dict,current=Depends(student)):
        with store.user_lock(current['id']):
            state=load(current['id'],pid);kind=payload.get('kind','A');access(pid,state,kind);memory=store.load_learning(current['id'],pid);version=learn.source_version(pid,state,kind)
            issue=next((i for i in learn.learning_evidence(pid,state,kind) if i['check_key']==probe_id),None)
            if not issue:raise HTTPException(409,'当前材料没有这项待辨别错误。')
            answer=payload.get('answer','');steps=payload.get('steps',{})
            if not isinstance(answer,str) or not 1<=len(answer.strip())<=2000 or not isinstance(steps,dict):raise HTTPException(422,'请说明实际计算方法或复现步骤。')
            probe={'check_key':probe_id,'question':issue.get('probe',{}).get('question','说明计算方法或复现步骤'),'source_version':version,'answered':True,'answer':answer,'reported_steps':steps,'source':'student_report','created':time.time()}
            if pid=='retail' and probe_id in learn.course.METRIC_LABELS:
                from .grading import diagnose_metrics,reference
                try:probe['diagnoses']=diagnose_metrics(state['metrics'],reference()['metrics'],{probe_id:steps},state['data_revision'])
                except ValueError as e:raise HTTPException(422,str(e))
            memory['probes'][probe_id]=probe;learn.event(memory,'probe_answered',check_key=probe_id,source_version=version);save(current['id'],pid,memory);return reply(current['id'],pid,state,kind)

    @app.post('/api/projects/{pid}/learning/plan')
    def plan(pid:str,payload:dict,current=Depends(student)):
        kind=payload.get('kind','A');skill=payload.get('skill_id');basic=payload.get('basic',False)
        if type(basic)is not bool:raise HTTPException(422,'基础模式须为布尔值。')
        with store.user_lock(current['id']):
            state=load(current['id'],pid);access(pid,state,kind);memory=store.load_learning(current['id'],pid);version=learn.source_version(pid,state,kind)
            if skill is not None and (not isinstance(skill,str) or skill not in templates.KINDS[pid]):raise HTTPException(422,'请选择当前项目中的有效练习方向。')
            if basic or not app.state.model_config.enabled:
                try:prepared=learn.basic_plan(memory,pid,state,skill,kind)
                except ValueError as e:raise HTTPException(409,str(e))
                save(current['id'],pid,memory);return plan_reply(current['id'],pid,state,kind,memory,prepared=prepared)
            active=next((e for e in reversed(memory['exercises']) if e['source_version']==version and e['status']=='active' and e['source'] in ('ai','teacher') and (skill is None or e['skill_id']==skill)),None)
            if active:return plan_reply(current['id'],pid,state,kind,memory,existing=active)
            base=engineering_context(state,'engineering_feedback',kind) if pid!='retail' else retail_context(state,'feedback')
            context=learn.adaptive_context(memory,pid,state,base,kind=kind)
            if skill:context['selected_skill']=skill;context['exercise_catalog']={k:v for k,v in context['exercise_catalog'].items() if v['skill_id']==skill};context['learning_issues']=[i for i in context['learning_issues'] if i['skill_id']==skill]
            context['probe_responses']={k:v for k,v in memory['probes'].items() if v['source_version']==version}
            needs_probe=pid=='retail' and any(i['check_key'] in learn.course.METRIC_LABELS and not context['probe_responses'].get(i['check_key'],{}).get('answered') and i['status']!='confirmed_step_error' for i in context['learning_issues'])
            context['required_action']='request_error_probe' if needs_probe else 'create_variant_exercise'
            context['replace_basic_exercises']=True
            # Any state change, even same material revision, must invalidate cache.
            fingerprint=hashlib.sha256(json.dumps({'source_version':version,'issues':context['learning_issues'],'probes':{k:v for k,v in context['probe_responses'].items() if v.get('answered')},'exercises':context['learning_history']['exercises'],'skill':skill,'model':app.state.model_config.model,'prompt_version':learn.PROMPT_VERSION},ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            cached=next((p for p in memory['plans'] if p['fingerprint']==fingerprint and p['status']=='ok'),None)
            if cached:return plan_reply(current['id'],pid,state,kind,memory,run=cached['run'],cached=True)
            if any(p['status']=='running' and time.time()-p.get('created',0)<360 for p in memory['plans']):raise HTTPException(409,'AI正在安排此项目的练习，请等待当前请求完成；不会重复调用模型。')
            request_id=secrets.token_hex(8)
            memory['plans'].append({'fingerprint':fingerprint,'status':'running','request_id':request_id,'created':time.time()});save(current['id'],pid,memory)
            draft=copy.deepcopy(memory);state_revision=state.get('revision',0)
        result=run_agent('adaptive_plan',context,app.state.model_config,learn.adaptive_tools(draft,pid,context))
        if result['status']=='ok' and not any(a['tool']==context['required_action'] and a['executed'] for a in result['actions']):
            result.update(status='no_action',message='AI未完成本次练习安排，原练习已保留。请稍后重试，或选择「不用AI，先做基础练习」。',needs_human_review=True)
        with store.user_lock(current['id']):
            latest=load(current['id'],pid);latest_memory=store.load_learning(current['id'],pid)
            fresh=learn.source_version(pid,latest,kind)==version and latest.get('revision',0)==state_revision and latest_memory==memory
            result.update(id=secrets.token_hex(8),purpose='adaptive_plan',created=time.time(),actions_committed=result['status']=='ok' and fresh)
            if not fresh:result.update(status='stale',message='材料或学习记录已更新，本次旧版本安排未应用。请重新安排。')
            target=draft if result['status']=='ok' else latest_memory
            reservation=next(p for p in target['plans'] if p.get('request_id')==request_id)
            reservation.update(status=result['status'],run=result);save(current['id'],pid,target)
            latest['agent_runs'].append(result)
            if result['needs_human_review']:latest['human_reviews'].append({'id':secrets.token_hex(6),'status':'pending','reason':result['message'],'created':time.time()})
            store.save_project(current['id'],pid,latest)
            return plan_reply(current['id'],pid,latest,kind,target,run=result)

    @app.post('/api/projects/{pid}/learning/exercises/{eid}/attempts')
    def attempt(pid:str,eid:str,payload:dict,current=Depends(student)):
        with store.user_lock(current['id']):
            state=load(current['id'],pid);kind=payload.get('kind','A');access(pid,state,kind);memory=store.load_learning(current['id'],pid);ex=checked_exercise(memory,pid,state,eid,kind)
            aid=payload.get('attempt_id')
            if not isinstance(aid,str) or not 1<=len(aid)<=80:raise HTTPException(422,'需要有效作答编号。')
            try:result=learn.grade_attempt(memory,eid,payload.get('answer'),aid)
            except ValueError as e:raise HTTPException(422,str(e))
            recent=[e for e in memory['exercises'] if e['source_version']==ex['source_version'] and e['skill_id']==ex['skill_id'] and e['attempts']][-2:]
            failures=sum(not e['attempts'][-1]['passed'] for e in recent)
            if failures>=2 and not any(r.get('learning_skill')==ex['skill_id'] and r['status']=='pending' for r in state['human_reviews']):
                state['human_reviews'].append({'id':secrets.token_hex(6),'status':'pending','reason':'两个新实例仍未通过：'+ex['skill_id'],'learning_skill':ex['skill_id'],'created':time.time()});store.save_project(current['id'],pid,state)
            save(current['id'],pid,memory);return {**reply(current['id'],pid,state,kind),'attempt':result}

    @app.post('/api/projects/{pid}/learning/exercises/{eid}/hints')
    def hint(pid:str,eid:str,payload:dict,current=Depends(student)):
        with store.user_lock(current['id']):
            state=load(current['id'],pid);kind=payload.get('kind','A');access(pid,state,kind);memory=store.load_learning(current['id'],pid);checked_exercise(memory,pid,state,eid,kind)
            try:learn.reveal_hint(memory,eid)
            except ValueError as e:raise HTTPException(409,str(e))
            save(current['id'],pid,memory);return reply(current['id'],pid,state,kind)

    @app.post('/api/projects/{pid}/learning/exercises/{eid}/next')
    def next_exercise(pid:str,eid:str,payload:dict,current=Depends(student)):
        with store.user_lock(current['id']):
            state=load(current['id'],pid);kind=payload.get('kind','A');access(pid,state,kind);memory=store.load_learning(current['id'],pid);ex=checked_exercise(memory,pid,state,eid,kind)
            if ex['status']=='active' and not ex['attempts']:raise HTTPException(409,'请先作答本题，再生成新的实例。')
            if ex['status']=='active':ex.update(status='abandoned',abandoned=True);learn.event(memory,'abandon',exercise_id=eid,skill_id=ex['skill_id'],source_version=ex['source_version'])
            try:learn.basic_plan(memory,pid,state,ex['skill_id'],kind,'verification')
            except ValueError as e:raise HTTPException(409,str(e))
            save(current['id'],pid,memory);return reply(current['id'],pid,state,kind)

    @app.post('/api/projects/{pid}/learning/exercises/{eid}/explanation')
    def explanation(pid:str,eid:str,payload:dict,current=Depends(student)):
        kind=payload.get('kind','A')
        with store.user_lock(current['id']):
            state=load(current['id'],pid);access(pid,state,kind);memory=store.load_learning(current['id'],pid);ex=checked_exercise(memory,pid,state,eid,kind)
            if ex['status']!='active':raise HTTPException(409,'本题已结束，请查看已有解释，或为新的练习请求AI解释。')
            if ex.get('explanation') and ex.get('explanation_attempt_count')==len(ex['attempts']):return reply(current['id'],pid,state,kind)
            if not app.state.model_config.enabled:raise HTTPException(409,'基础模式请使用分级提示，AI尚未连接。')
            base=engineering_context(state,'engineering_feedback',kind) if pid!='retail' else retail_context(state,'feedback')
            context=learn.adaptive_context(memory,pid,state,base,eid,kind);context.update(current_exercise_id=eid)
            draft=copy.deepcopy(memory);result=run_agent('adaptive_feedback',context,app.state.model_config,{'explain_learning_attempt':learn.adaptive_tools(draft,pid,context)['explain_learning_attempt']})
            result.update(id=secrets.token_hex(8),purpose='adaptive_feedback',created=time.time(),actions_committed=result['status']=='ok')
            if result['status']=='ok':draft_ex=learn.find_exercise(draft,eid);draft_ex['explanation_attempt_count']=len(ex['attempts']);save(current['id'],pid,draft)
            state['agent_runs'].append(result);store.save_project(current['id'],pid,state)
            return {**reply(current['id'],pid,state,kind),'run':result}

    @app.get('/api/operator/learning')
    def operator_learning(include_demo:bool=False,current=Depends(founder)):
        records=[]
        for user in store.list_users():
            if user['role']!='student' or (user['is_demo'] and not include_demo):continue
            for pid in templates.PROJECTS:
                memory=store.load_learning(user['id'],pid)
                if not memory['events']:continue
                records.append({'learner':user['id'][:8],'project':pid,'is_demo':bool(user['is_demo']),'events':memory['events'],'exercise_count':len(memory['exercises']),'assisted_passes':sum(e['status']=='passed' and e['assisted'] for e in memory['exercises']),'first_unassisted_passes':sum(bool(e['attempts']) and e['attempts'][0]['passed'] and not e['assisted'] for e in memory['exercises'])})
        return {'records':records,'distinct_learners':len({r['learner'] for r in records}),'course_records':len(records),'note':'仅平台内练习记录，不能替代真人学习效果；演示账号默认排除。'}
