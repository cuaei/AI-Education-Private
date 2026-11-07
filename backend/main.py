import copy
import asyncio
import hashlib
import csv
import io
import json
import math
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import Response, JSONResponse, FileResponse
from . import course, grading
from .agent import ModelConfig, run_agent
from .config import load_env, model_config
from .storage import Store
from .portfolio import progress, objective_score, public_portfolio, export_html, export_markdown
from .projects import mount_projects
from .learning_chat import mount_chat
from .registration import mount_registration
from .engineering_runner import stop_user_previews
from . import engineering_course as engineering
from . import learning
from .learning_routes import mount_learning
from .tutorial import mount_tutorial
from .java_route import mount_java_route
from .java_course import mount_java_course
from .teacher_routes import mount_teacher
from .engineering_agent import context_for as engineering_context


def public_user(user):
    return {k:user[k] for k in ('id','username','role','is_demo')}


def evidence(state):
    result={}
    if state['diagnostic']:result['diagnostic:1']=state['diagnostic']
    version=state['data_revision']
    for k,v in state['metrics'].items():
        result[f'metric:{version}:{k}']={'label':course.METRIC_LABELS[k],'value':v,'verified':bool((state['grades']['metrics'] or {}).get('passed'))}
    if (state['grades']['groups'] or {}).get('passed'):
        for dim in ('category','channel','weeks'):
            rows=state['tables'].get(dim,[])
            for row in rows:result[f'group:{version}:{dim}:{row["name"]}']=row
    if state['report']:result['report:'+state['report']['id']]=state['report']
    for i,turn in enumerate(state['defense']):
        if turn.get('answer'):result[f'defense:{i+1}']=turn
    if state['submissions']:result['submission:'+state['submissions'][-1]['id']]=state['submissions'][-1]
    return result


def context_for(state,purpose):
    facts=evidence(state)
    allowed=[course.STAGES[progress(state)['stage']]]+[course.CARDS[s]['title'] for s in (state['diagnostic'] or {}).get('weak_skills',[])]
    return {'purpose':purpose,'evidence_ids':list(facts),'facts':facts,'allowed_next_tasks':allowed,'skill_catalog':{k:{'title':v['title']} for k,v in course.CARDS.items()},'student_memory':{'diagnostic':state['diagnostic'],'remediation':state['remediation'],'next_task':state['next_task']},'grades':state['grades'],'report_stale':state['report_stale'],'defense_snapshot':state['defense_snapshot'],'course':{'version':course.VERSION,'metrics':course.METRIC_LABELS,'policy':'人民币元；比率为百分数；净销售额扣退款；隔离缺失和冲突记录；描述性分析不能证明因果。'}}


def tools_for(state,purpose,learning_assignment=None):
    facts=evidence(state)
    def card(args):
        skill=args['skill_id']
        if skill not in course.CARDS:raise ValueError('未知技能')
        return {k:v for k,v in course.CARDS[skill].items() if k!='answer'}
    def remediation(args):
        if args['skill_id'] not in course.CARDS or type(args['hint_level']) is not int or args['hint_level'] not in (1,2,3):raise ValueError('无效补练')
        item={'id':secrets.token_hex(6),'skill_id':args['skill_id'],'hint_level':args['hint_level'],'completed':False,'attempts':0}
        state['remediation'].append(item)
        return {'exercise':{**item,**card(args)}}
    def next_task(args):
        stage=progress(state)['stage']
        allowed=[course.STAGES[stage]]+[course.CARDS[s]['title'] for s in (state['diagnostic'] or {}).get('weak_skills',[])]
        if args['task'] not in allowed or len(args['reason'])>1000:raise ValueError('任务依赖不符')
        state['next_task']=args['task'];return {'next_task':args['task']}
    def human(args):
        if not isinstance(args['reason'],str) or not 1<=len(args['reason'])<=1000:raise ValueError('缺少复核理由')
        state['human_reviews'].append({'id':secrets.token_hex(6),'reason':args['reason'],'status':'pending','created':time.time()})
        return {'status':'已加入人工复核队列'}
    def question(args):
        if args['evidence_id'] not in facts or not 1<=len(args['question'])<=1000:raise ValueError('问题证据错误')
        item={'question':args['question'],'evidence_id':args['evidence_id'],'answer':'','source':'ai'}
        if state['defense'] and not state['defense'][-1]['answer']:state['defense'][-1]=item
        elif len(state['defense'])<5:state['defense'].append(item)
        else:raise ValueError('答辩问题已达上限')
        return item
    def assessment(args,kind):
        names=['观察与假设区分','证据','建议可执行性','验证方法','限制说明'] if kind=='report' else ['指标理解','方法解释','限制理解']
        rows=args['criteria']
        report=state['report'] or {}
        texts=[r['text'] for r in report.get('observations',[])]+[r['text'] for r in report.get('recommendations',[])]+[r.get('validation','') for r in report.get('recommendations',[])]+[report.get('limitations','')]
        if not isinstance(rows,list) or len(rows)!=len(names) or not all(isinstance(r,dict) for r in rows) or {r.get('criterion') for r in rows}!=set(names):raise ValueError('量表不完整')
        for r in rows:
            quote=r.get('quote');eid=r.get('evidence_id')
            source_texts=texts if kind=='report' and eid=='report:'+str(report.get('id')) else ([facts[eid]['answer']] if kind=='defense' and isinstance(eid,str) and eid.startswith('defense:') and eid in facts else [])
            if type(r.get('score')) is not int or not 0<=r['score']<=5 or not isinstance(quote,str) or not quote or not any(quote in text for text in source_texts) or not isinstance(r.get('reason'),str) or not 1<=len(r['reason'])<=1000:raise ValueError('评价须引用对应报告原文或答辩回答，不能引用生成的编号。')
        review={'criteria':rows,'score':sum(r['score'] for r in rows),'max_score':len(names)*5,'source':'ai','created':time.time()}
        state[kind+'_review']=review;return review
    read={'inspect_submission':lambda args:{'latest':state['submissions'][-1] if state['submissions'] else None},'check_metrics':lambda args:{'evaluation':state['grades']['metrics'],'evidence_ids':list(facts)},'lookup_skill_card':card}
    if purpose=='diagnosis':return {**read,'propose_next_task':next_task,'request_human_review':human}
    if purpose=='feedback':return {**read,'assign_remediation':learning_assignment or remediation,'propose_next_task':next_task,'request_human_review':human}
    if purpose=='report':return {**read,'review_report':lambda args:assessment(args,'report'),'request_human_review':human}
    if purpose=='defense':
        tools={**read,'ask_defense_question':question,'request_human_review':human}
        if sum(bool(t['answer']) for t in state['defense'])>=3:tools['review_defense']=lambda args:assessment(args,'defense')
        return tools
    if purpose=='portfolio':return {'build_portfolio':lambda args:public_portfolio(state),'request_human_review':human}
    return {}


def create_app(data_dir=None,demo=None):
    load_env();demo=(os.environ.get('DEMO_MODE','true').lower()=='true') if demo is None else demo
    root=Path(data_dir or os.environ.get('DATA_DIR','runtime')).resolve();root.mkdir(parents=True,exist_ok=True)
    store=Store(root/'training.sqlite');app=FastAPI(title='我要实习',docs_url='/api/docs');app.state.store=store;app.state.model_config=model_config();app.state.root=root
    if not store.find_user('founder'):
        password='Founder2026!' if demo else os.environ.get('FOUNDER_PASSWORD','')
        if len(password)<10:raise ValueError('非演示环境需设置至少十位的 FOUNDER_PASSWORD。')
        store.create_user('founder',password,'founder',demo)
    if demo:
        if not store.find_user('teacher'):store.create_user('teacher','Teach2026!','teacher',True)
        for username in ('student','student2'):
            if not store.find_user(username):store.create_user(username,'Study2026!','student',True)
    login_attempts={};operation_locks={}

    @app.middleware('http')
    async def guard(request,call_next):
        if request.method in ('POST','PUT','DELETE','PATCH'):
            origin=request.headers.get('origin')
            allowed={str(request.base_url).rstrip('/'),'http://127.0.0.1:5173','http://localhost:5173','http://127.0.0.1:8000','http://localhost:8000'}
            if origin and origin not in allowed:return JSONResponse({'detail':'请求来源不允许。'},status_code=403)
            try:
                limit=(5*1024*1024+8192) if request.url.path.startswith('/api/projects/software-engineering/submission/') else (2*1024*1024+8192)
                if int(request.headers.get('content-length','0'))>limit:return JSONResponse({'detail':'请求过大。'},status_code=413)
            except ValueError:return JSONResponse({'detail':'无效请求长度。'},status_code=400)
        key=request.headers.get('Idempotency-Key')
        current=store.session_user(request.cookies.get('studio_session','')) if key else None
        eligible=request.method=='POST' and not request.url.path.startswith('/api/auth/') and current
        if not eligible:return await call_next(request)
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',key):return JSONResponse({'detail':'操作编号无效。'},status_code=422)
        content=await request.body()
        boundary=re.search(r'boundary=([^;]+)',request.headers.get('content-type',''))
        if boundary:content=content.replace(boundary[1].strip('"').encode(),b'STABLE_BOUNDARY')
        fingerprint=hashlib.sha256(request.url.path.encode()+b'\0'+content).hexdigest()
        async with operation_locks.setdefault((current['id'],key),asyncio.Lock()):
            previous=store.operation(current['id'],key)
            if previous:
                if previous['fingerprint']!=fingerprint:return JSONResponse({'detail':'同一操作编号不能用于不同内容，请重新提交。'},status_code=409)
                return Response(previous['body'],status_code=previous['status'],media_type=previous['media_type'])
            response=await call_next(request)
            if 200<=response.status_code<300:
                body=b''.join([chunk async for chunk in response.body_iterator])
                media=response.headers.get('content-type','application/json')
                store.save_operation(current['id'],key,fingerprint,body,response.status_code,media)
                return Response(body,status_code=response.status_code,headers=dict(response.headers))
            return response

    def user(request:Request):
        found=store.session_user(request.cookies.get('studio_session',''))
        if not found:raise HTTPException(401,'请登录后继续。')
        return found

    def student(current=Depends(user)):
        if current['role']!='student':raise HTTPException(403,'该功能属于学生训练空间。')
        return current

    def founder(current=Depends(user)):
        if current['role']!='founder':raise HTTPException(403,'仅创业者可访问。')
        return current

    def teacher(current=Depends(user)):
        if current['role']!='teacher':raise HTTPException(403,'此功能仅供教师使用。')
        return current

    def state_response(current):
        state=store.load(current['id']);return {**state,'user':public_user(current),'progress':progress(state),'objective_score':objective_score(state),'evidence':evidence(state),'mode':'ai' if app.state.model_config.enabled else 'basic'}

    def require(condition,message):
        if not condition:raise HTTPException(409,message)

    def save(current,state):store.save(current['id'],state);return state_response(current)

    def archive_work(state):
        if state['report'] or state['defense'] or state['transfer']:
            snapshot={k:copy.deepcopy(state[k]) for k in ('report','report_review','defense','defense_snapshot','defense_review','transfer','metrics','tables','data_revision')}
            if not state['work_history'] or state['work_history'][-1].get('snapshot')!=snapshot:
                state['work_history'].append({'report':snapshot['report'],'snapshot':snapshot,'created':time.time()})

    def invalidate(state):
        archive_work(state)
        state['data_revision']+=1;state['report_stale']=bool(state['report']);state['report_review']=None;state['defense']=[];state['defense_snapshot']=None;state['defense_review']=None;state['transfer']=None;state['portfolio_note']=''

    def text_limit(payload):
        if len(json.dumps(payload,ensure_ascii=False))>6000:raise HTTPException(422,'文本过长，请将本次内容控制在 4,000 字以内。')

    @app.get('/api/public')
    def public():
        return {'name':'我要实习','version':course.VERSION,'stages':course.STAGES,'metrics':course.METRIC_LABELS,'quiz_c':course.quiz_public('C'),'quiz_d':course.quiz_public('D'),'cards':{k:{a:b for a,b in v.items() if a!='answer'} for k,v in course.CARDS.items()},'mode':'ai' if app.state.model_config.enabled else 'basic','demo':demo,'data_note':'自制合成数据 · 每份 512 条有效订单 · 5 条重复副本 · 3 条缺失记录'}

    @app.post('/api/auth/login')
    def login(payload:dict,request:Request):
        ip=request.client.host if request.client else 'local';now=time.time();attempts=[t for t in login_attempts.get(ip,[]) if now-t<60]
        if len(attempts)>=10:raise HTTPException(429,'登录尝试过多，请一分钟后再试。')
        username=payload.get('username');password=payload.get('password')
        if not isinstance(username,str) or not isinstance(password,str) or len(password)>200:raise HTTPException(422,'账号或密码格式不正确。')
        current=store.authenticate(username,password)
        if not current:login_attempts[ip]=attempts+[now];raise HTTPException(401,'账号或密码不正确。')
        login_attempts.pop(ip,None);result=JSONResponse(public_user(current));result.set_cookie('studio_session',store.session(current['id']),httponly=True,samesite='strict',secure=os.environ.get('COOKIE_SECURE','false').lower()=='true',max_age=86400);return result

    @app.post('/api/auth/logout')
    def logout(request:Request):
        store.logout(request.cookies.get('studio_session',''));response=JSONResponse({'ok':True});response.delete_cookie('studio_session');return response

    @app.get('/api/me')
    def me(current=Depends(user)):return public_user(current)

    @app.get('/api/state')
    def get_state(current=Depends(student)):return state_response(current)

    @app.post('/api/diagnostic')
    def diagnostic(payload:dict,current=Depends(student)):
        with store.user_lock(current['id']):
            state=store.load(current['id'])
            require(state['diagnostic'] is None,'诊断已经完成。起点测评不接受重复刷分。')
            try:state['diagnostic']=course.quiz_grade(payload.get('answers',[]),state['diagnostic_form'])
            except ValueError as e:raise HTTPException(422,str(e))
            state['report_stale']=bool(state['report']);state['next_task']='数据检查';return save(current,state)

    @app.get('/api/data/{kind}')
    def get_data(kind:str,current=Depends(student)):
        if kind in ('A','B'):content=course.dataset(kind)
        elif kind=='metrics-template':content=('key,value\n'+'\n'.join(k+',' for k in course.METRIC_LABELS)).encode('utf-8-sig')
        elif kind=='groups-template':content=('dimension,name,baseline,current\n'+'\n'.join(f'{dim},{row["name"]},,' for dim,rows in grading.reference('A')['groups'].items() for row in rows)).encode('utf-8-sig')
        else:raise HTTPException(404,'文件不存在。')
        return Response(content,media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{kind}.csv"'})

    def add_submission(state,kind,values,evaluation):
        item={'id':secrets.token_hex(8),'version':len(state['submissions'])+1,'kind':kind,'values':values,'evaluation':evaluation,'created':time.time()}
        state['submissions'].append(item);return item

    @app.post('/api/submit/clean')
    def submit_clean(file:UploadFile=File(...),current=Depends(student)):
        with store.user_lock(current['id']):
            state=store.load(current['id']);require(state['diagnostic'],'请先完成起点诊断。')
            content=file.file.read(2*1024*1024+1)
            try:result=grading.evaluate_clean_csv(content)
            except ValueError as e:raise HTTPException(422,str(e))
            invalidate(state);state['grades']={'clean':result,'metrics':None,'groups':None};state['metrics']={};state['tables']={}
            item=add_submission(state,'clean',{'filename':Path(file.filename or 'data.csv').name},result)
            folder=root/'uploads'/current['id'];folder.mkdir(parents=True,exist_ok=True);(folder/(item['id']+'.csv')).write_bytes(content)
            state['next_task']='指标分析' if result['passed'] else '数据检查';return save(current,state)

    def finite_metrics(values):
        if not isinstance(values,dict) or set(values)!=set(course.METRIC_LABELS):raise HTTPException(422,'请填写全部五个指标。')
        cleaned={}
        for key,value in values.items():
            try:
                if value is None:cleaned[key]=None;continue
                number=float(value)
                if not math.isfinite(number):raise ValueError()
                cleaned[key]=number
            except (ValueError,TypeError):raise HTTPException(422,'指标须为有限数字，百分数填写 20 而不是 0.2。')
        return cleaned

    def metrics_submit(values,current,steps=None):
        values=finite_metrics(values)
        with store.user_lock(current['id']):
            state=store.load(current['id']);require((state['grades']['clean'] or {}).get('passed'),'请先通过数据检查。')
            try:result=grading.compare_metrics(values,grading.reference()['metrics'],steps,str(state['data_revision']+1))
            except ValueError as e:raise HTTPException(422,str(e))
            invalidate(state);state['grades']['metrics']=result;state['grades']['groups']=None;state['metrics']=values;state['tables']={};add_submission(state,'metrics',values,result);state['next_task']='图表证据' if result['passed'] else '指标分析';return save(current,state)

    @app.post('/api/submit/metrics')
    def metrics(payload:dict,current=Depends(student)):
        steps=payload.get('steps')
        if steps is not None and (not isinstance(steps,dict) or set(steps)-set(course.METRIC_LABELS)):raise HTTPException(422,'计算步骤字段不正确。')
        return metrics_submit(payload.get('values'),current,steps)

    @app.post('/api/submit/metrics-file')
    def metrics_file(file:UploadFile=File(...),current=Depends(student)):
        try:
            content=file.file.read(2*1024*1024+1)
            if len(content)>2*1024*1024:raise ValueError()
            rows=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
            if len(rows)!=5 or len({r['key'] for r in rows})!=5:raise ValueError()
            return metrics_submit({r['key']:r['value'] for r in rows},current)
        except (ValueError,KeyError,UnicodeError,csv.Error):raise HTTPException(422,'请使用五行 key,value 指标模板。')

    @app.post('/api/submit/groups')
    def groups(payload:dict,current=Depends(student)):
        with store.user_lock(current['id']):
            state=store.load(current['id']);require((state['grades']['metrics'] or {}).get('passed'),'请先通过指标核验。')
            tables=payload.get('tables');require(isinstance(tables,dict),'需要提交分组表。')
            text_limit(tables)
            try:result=grading.compare_groups(tables)
            except (TypeError,ValueError,KeyError):raise HTTPException(422,'分组表格式不正确。')
            invalidate(state);state['grades']['groups']=result;state['tables']=tables;add_submission(state,'groups',tables,result);state['next_task']='报告审阅' if result['passed'] else '图表证据';return save(current,state)

    @app.post('/api/remediation')
    def assign_practice(payload:dict,current=Depends(student)):
        with store.user_lock(current['id']):
            state=store.load(current['id']);skill=payload.get('skill_id')
            if skill not in course.CARDS:raise HTTPException(422,'未知技能。')
            state['remediation'].append({'id':secrets.token_hex(6),'skill_id':skill,'hint_level':1,'completed':False,'attempts':0,'source':'basic'});return save(current,state)

    @app.post('/api/remediation/{exercise_id}')
    def answer_practice(exercise_id:str,payload:dict,current=Depends(student)):
        with store.user_lock(current['id']):
            state=store.load(current['id']);item=next((x for x in state['remediation'] if x['id']==exercise_id),None)
            if not item:raise HTTPException(404,'练习不存在。')
            if item.get('adaptive'):raise HTTPException(409,'这是新变式练习，请在“我的针对性练习”中作答。')
            item['attempts']+=1;item['completed']=grading.close_number(payload.get('answer'),course.CARDS[item['skill_id']]['answer']);item['hint_level']=min(3,1+item['attempts']) if not item['completed'] else item['hint_level'];return save(current,state)

    @app.post('/api/report')
    def report(payload:dict,current=Depends(student)):
        text_limit(payload)
        with store.user_lock(current['id']):
            state=store.load(current['id']);require(objective_score(state)==60,'请先完成全部客观核验。')
            observations=payload.get('observations',[]);recommendations=payload.get('recommendations',[]);limitations=payload.get('limitations','');facts=evidence(state)
            if not isinstance(observations,list) or not 1<=len(observations)<=5 or not isinstance(recommendations,list) or not 2<=len(recommendations)<=5 or not isinstance(limitations,str) or not limitations.strip():raise HTTPException(422,'需要至少一项观察、两项建议及限制说明。')
            for row in observations+recommendations:
                if not isinstance(row,dict) or not isinstance(row.get('text'),str) or not row['text'].strip() or row.get('evidence_id') not in facts or not row['evidence_id'].startswith(('metric:','group:')):raise HTTPException(422,'每项结论和建议必须绑定当前指标证据。')
            if any(not isinstance(r.get('validation'),str) or not r['validation'].strip() for r in recommendations):raise HTTPException(422,'每项建议需要验证方法。')
            archive_work(state)
            state['report']={'id':secrets.token_hex(8),'data_revision':state['data_revision'],'observations':observations,'recommendations':recommendations,'limitations':limitations};state['report_stale']=False;state['report_review']=None;state['defense']=[];state['defense_snapshot']=None;state['defense_review']=None;state['transfer']=None;state['next_task']='作品答辩';return save(current,state)

    fixed_questions=['请解释你采用的净销售额和退款率计算口径。','选一项建议，解释数据如何支持它，以及你将如何验证。','这份交易数据不能回答哪些问题？你需要补充什么证据？']

    @app.post('/api/defense/start')
    def start_defense(current=Depends(student)):
        with store.user_lock(current['id']):
            state=store.load(current['id']);require(state['report'] and not state['report_stale'],'请先提交有效报告。')
            if not state['defense']:
                state['defense_snapshot']=public_portfolio(state);state['defense']=[{'question':fixed_questions[0],'evidence_id':'report:'+state['report']['id'],'answer':'','source':'basic'}]
            return save(current,state)

    @app.post('/api/defense/answer')
    def defense_answer(payload:dict,current=Depends(student)):
        answer=payload.get('answer','')
        if not isinstance(answer,str) or not 1<=len(answer.strip())<=4000:raise HTTPException(422,'请填写 1–4,000 字的回答。')
        with store.user_lock(current['id']):
            state=store.load(current['id']);require(state['defense'] and not state['report_stale'],'请先开始有效作品的答辩。');require(not state['defense'][-1]['answer'],'当前问题已经作答。')
            state['defense'][-1]['answer']=answer;count=sum(bool(t['answer']) for t in state['defense'])
            if count<3:state['defense'].append({'question':fixed_questions[count],'evidence_id':'report:'+state['report']['id'],'answer':'','source':'basic'})
            state['defense_review']=None;state['next_task']='独立迁移' if count>=3 else '作品答辩';return save(current,state)

    @app.post('/api/transfer')
    def transfer(payload:dict,current=Depends(student)):
        values=finite_metrics(payload.get('values'))
        with store.user_lock(current['id']):
            state=store.load(current['id']);require(not state['report_stale'] and sum(bool(t['answer']) for t in state['defense'])>=3,'请先完成有效作品的三题答辩。');require(state['transfer'] is None,'独立测评已经提交，不接受反复刷分。')
            try:posttest=course.quiz_grade(payload.get('answers',[]),'D' if state['diagnostic_form']=='C' else 'C')
            except ValueError as e:raise HTTPException(422,str(e))
            state['transfer']={'evaluation':grading.compare_metrics(values,grading.reference('B')['metrics']),'posttest':posttest,'values':values,'mode':'independent','created':time.time()};state['next_task']='作品交付';return save(current,state)

    @app.post('/api/coach')
    def coach(payload:dict,request:Request,current=Depends(student)):
        purpose=payload.get('purpose')
        if purpose not in ('diagnosis','feedback','report','defense','portfolio'):raise HTTPException(422,'未知教练任务。')
        with store.user_lock(current['id']):
            original=store.load(current['id']);draft=copy.deepcopy(original)
            if purpose in ('report','defense','portfolio'):require(original['report'] and not original['report_stale'],'请先提交有效报告。')
            if purpose=='defense':require(original['defense'],'请先开始答辩。')
            key=request.headers.get('Idempotency-Key')
            if key:
                existing=next((r for r in original['agent_runs'] if r.get('request_key')==key),None)
                if existing:return existing
            require(not learning.independent('retail',original),'当前为独立测评，不能使用针对答案的教练。')
            learning_draft=store.load_learning(current['id'],'retail')
            context=learning.adaptive_context(learning_draft,'retail',draft,context_for(draft,purpose))
            result=run_agent(purpose,context,app.state.model_config,tools_for(draft,purpose,lambda args:learning.legacy_assignment(learning_draft,'retail',draft,args)))
            if result['mode']=='basic':return result
            result.update(id=secrets.token_hex(8),purpose=purpose,created=time.time(),request_key=key)
            target=draft if result['status']=='ok' else original
            result['actions_committed']=result['status']=='ok'
            if result['status']=='ok':store.save_learning(current['id'],'retail',learning_draft)
            if result['needs_human_review'] and not any(x['status']=='pending' for x in target['human_reviews']):target['human_reviews'].append({'id':secrets.token_hex(6),'reason':result['message'],'status':'pending','created':time.time()})
            target['agent_runs'].append(result);target['feedback'].append({'purpose':purpose,'message':result['message'],'evidence_ids':result['evidence_ids'],'created':time.time()});store.save(current['id'],target);return result

    @app.post('/api/portfolio/note')
    def note(payload:dict,current=Depends(student)):
        text=payload.get('text','')
        if not isinstance(text,str) or len(text)>4000:raise HTTPException(422,'补充说明最多 4,000 字。')
        with store.user_lock(current['id']):state=store.load(current['id']);state['portfolio_note']=text;return save(current,state)

    @app.get('/api/portfolio')
    def portfolio(current=Depends(student)):return public_portfolio(store.load(current['id']))

    @app.get('/api/export/{format}')
    def export(format:str,current=Depends(student)):
        state=store.load(current['id'])
        if format=='json':return Response(json.dumps(state,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="private-training-records.json"'})
        if format not in ('html','md'):raise HTTPException(404,'格式不存在。')
        return Response(export_html(state) if format=='html' else export_markdown(state),media_type='text/html' if format=='html' else 'text/markdown',headers={'Content-Disposition':f'attachment; filename="career-portfolio.{format}"'})

    @app.post('/api/share')
    def share(payload:dict={},current=Depends(student)):
        if any(type(payload.get(k,False)) is not bool for k in ('include_defense','include_reviews')):raise HTTPException(422,'分享选项须为开关。')
        return {'token':store.create_share(current['id'],public_portfolio(store.load(current['id']),payload.get('include_defense',False),payload.get('include_reviews',False)))}

    @app.delete('/api/share')
    def revoke(current=Depends(student)):store.revoke_shares(current['id']);return {'ok':True}

    @app.get('/api/shared/{token}')
    def shared(token:str):
        body=store.get_share(token)
        if not body:raise HTTPException(404,'分享不存在或已撤销。')
        return body

    @app.delete('/api/account')
    def delete_account(current=Depends(student)):
        with store.user_lock(current['id']):
            stop_user_previews(current['id'])
            engineering_folder=(root/'engineering'/current['id']).resolve()
            if engineering_folder.is_relative_to(root/'engineering') and engineering_folder.exists():
                import shutil
                shutil.rmtree(engineering_folder)
            folder=(root/'uploads'/current['id']).resolve()
            if folder.is_relative_to(root/'uploads') and folder.exists():
                for path in folder.glob('*.csv'):path.unlink()
                folder.rmdir()
            store.delete_user(current['id'])
        response=JSONResponse({'ok':True});response.delete_cookie('studio_session');return response

    def operator_data():
        learners=[];runs=[];human_minutes=0;engineering_learners=[]
        runs.extend(r for r in app.state.classrooms.all_runs() if r.get('mode')=='ai')
        for current in store.list_users():
            if current['role']!='student':
                runs.extend(store.load(current['id'])['agent_runs']);continue
            state=store.load(current['id']);runs.extend(state['agent_runs']);human_minutes+=sum(r.get('minutes',0) for r in state['human_reviews'])
            engineering_state=store.load_project(current['id'],engineering.PROJECT,engineering.initial_state)
            runs.extend(engineering_state['agent_runs']);human_minutes+=sum(r.get('minutes',0) for r in engineering_state['human_reviews'])
            if engineering_state['diagnostic']:
                engineering_learners.append({'is_demo':bool(current['is_demo']),'project_id':engineering.PROJECT,'progress':engineering.progress(engineering_state),'objective_score':(engineering_state['grade'] or {}).get('score',0),'pending_count':sum(r['status']=='pending' for r in engineering_state['human_reviews'])})
            learners.append({**public_user(current),'progress':progress(state),'objective_score':objective_score(state),'diagnostic_score':(state['diagnostic'] or {}).get('score'),'posttest_score':((state['transfer'] or {}).get('posttest') or {}).get('score'),'pending_reviews':[r for r in state['human_reviews'] if r['status']=='pending'],'history_reviews':state['human_reviews'],'ai_runs':len(state['agent_runs']),'cost':sum(r['cost'] for r in state['agent_runs'] if r['cost'] is not None),'cost_known':all(r['cost'] is not None for r in state['agent_runs']) and bool(state['agent_runs'])})
        return {'learners':learners,'engineering_learners':engineering_learners,'teachers':[public_user(u) for u in store.list_users() if u['role']=='teacher'],'summary':{'students':len(learners),'real_participants':sum(not r['is_demo'] for r in learners),'finished':sum(r['progress']['finished'] for r in learners)+sum(r['progress']['finished'] for r in engineering_learners),'human_minutes':human_minutes,'ai_runs':len(runs),'known_cost':sum(r['cost'] for r in runs if r['cost'] is not None),'unpriced_runs':sum(r['cost'] is None for r in runs),'currency':app.state.model_config.currency},'model':{'enabled':app.state.model_config.enabled,'model':app.state.model_config.model or None},'operator_feedback':store.load(store.find_user('founder')['id'])['feedback']}

    @app.get('/api/operator')
    def operator(current=Depends(founder)):return operator_data()

    @app.get('/api/operator/learners/{uid}')
    def learner_work(uid:str,current=Depends(founder)):
        learner=next((u for u in store.list_users() if u['id']==uid and u['role']=='student'),None)
        if not learner:raise HTTPException(404,'学员不存在。')
        return state_response(learner)

    @app.post('/api/operator/users')
    def create_student(payload:dict,current=Depends(founder)):
        username=payload.get('username','');password=payload.get('password','')
        role=payload.get('role','student')
        if role not in ('student','teacher'):raise HTTPException(422,'只可创建学生或教师账号。')
        if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9_-]{3,30}',username) or not isinstance(password,str) or not 10<=len(password)<=200:raise HTTPException(422,'账号需 3–30 位字母数字；密码至少十位。')
        try:return public_user(store.create_user(username,password,role))
        except sqlite3.IntegrityError:raise HTTPException(409,'账号已存在。')

    @app.post('/api/operator/review')
    def human_review(payload:dict,current=Depends(founder)):
        uid=payload.get('user_id');minutes=payload.get('minutes',0);comment=payload.get('note','')
        if not any(u['id']==uid and u['role']=='student' for u in store.list_users()):raise HTTPException(404,'学员不存在。')
        if type(minutes) is not int or not 0<=minutes<=600 or not isinstance(comment,str) or not 1<=len(comment)<=2000:raise HTTPException(422,'请填写复核意见及 0–600 分钟人工时间。')
        with store.user_lock(uid):
            state=store.load(uid)
            for review in state['human_reviews']:
                if review['status']=='pending':review['status']='resolved'
            state['human_reviews'].append({'id':secrets.token_hex(6),'status':'resolved','note':comment,'minutes':minutes,'created':time.time()})
            for name,maximum in (('report_review',25),('defense_review',15)):
                if name in payload:
                    require(state['report'] and not state['report_stale'],'需要有效报告才能评分。')
                    if name=='defense_review':require(sum(bool(t['answer']) for t in state['defense'])>=3,'需要完成三题答辩才能评分。')
                    score=payload[name]
                    if type(score) is not int or not 0<=score<=maximum:raise HTTPException(422,'人工评价分值超出量表。')
                    state[name]={'previous':state[name],'score':score,'max_score':maximum,'source':'human','reason':comment}
            store.save(uid,state);return {'ok':True}

    @app.post('/api/operator/insights')
    def insights(request:Request,current=Depends(founder)):
        with store.user_lock(current['id']):
            data=operator_data();anonymous={'summary':data['summary'],'objective_max_score':60,'policy':'演示账号只用于测试，不代表真实试用效果；客观核验60分为满分；未计价不代表免费。','learners':[{'learner':f'学员{i+1}','is_demo':bool(l['is_demo']),'progress':l['progress'],'objective_score':l['objective_score'],'pending_count':len(l['pending_reviews'])} for i,l in enumerate(data['learners'])]}
            context={'evidence_ids':['operator:summary'],'facts':anonymous}
            anonymous['engineering_learners']=data['engineering_learners']
            result=run_agent('operator',context,app.state.model_config,{'operator_insights':lambda args:anonymous})
            if result['mode']=='ai':
                state=store.load(current['id']);result.update(id=secrets.token_hex(8),purpose='operator',created=time.time());state['agent_runs'].append(result);state['feedback'].append({'message':result['message'],'purpose':'operator'});store.save(current['id'],state)
            return result

    @app.get('/api/operator/model-status')
    def model_status(current=Depends(founder)):
        cfg=app.state.model_config;return {'configured':cfg.enabled,'base_url':cfg.base_url,'model':cfg.model,'key_present':bool(cfg.api_key),'currency':cfg.currency}

    @app.get('/api/health')
    def health():return {'ok':True,'mode':'ai' if app.state.model_config.enabled else 'basic'}

    mount_registration(app,store)
    mount_teacher(app,store,user,student)
    mount_projects(app,store,student,founder,user,root)
    mount_chat(app,store,student,context_for)
    mount_learning(app,store,student,founder,context_for,engineering_context)
    mount_tutorial(app,store,student)
    mount_java_route(app,store,student)
    mount_java_course(app,store,student,founder,teacher)

    frontend=Path(__file__).resolve().parents[1]/'frontend'/'dist'
    @app.get('/{path:path}')
    def web(path:str):
        if path.startswith('api/'):raise HTTPException(404,'接口不存在。')
        file=(frontend/path).resolve()
        if file.is_relative_to(frontend) and file.is_file():return FileResponse(file)
        if (frontend/'index.html').exists():return FileResponse(frontend/'index.html')
        return JSONResponse({'message':'前端尚未构建，请运行前端构建命令。'})
    return app


app=create_app()
