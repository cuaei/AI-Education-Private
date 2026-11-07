"""Course catalogue and all engineering training API operations."""
import copy
import json
import secrets
import shutil
import threading
import time
import zipfile
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import Depends, HTTPException, File, UploadFile, Request
from fastapi.responses import Response, FileResponse
from . import engineering_course as course
from . import engineering_runner as runner
from .engineering_agent import context_for,tools_for
from .agent import run_agent
from . import learning
from .portfolio import progress as retail_progress

CATALOG=[{'id':'retail','title':'校园文创店销售分析与运营建议','professional':['商科','管理','数据分析'],'role':'运营与数据分析','description':'从原始交易CSV到分析、建议、答辩和作品交付。','technology':'CSV / 图表 / 分析报告','hours':'按阶段完成','deliverable':'分析作品集'}, {'id':course.PROJECT,'title':course.TITLE,'professional':['软件工程','计算机'],'role':'初级全栈工程师','description':'接手有缺陷的活动报名系统，修复、联调、测试并交付。','technology':'Python / FastAPI / React / TypeScript','hours':'16—24小时（设计估计）','deliverable':'可运行源码与工程作品集'}]
for item in CATALOG:
    item['availability']='available'
# Catalogue placeholders have no training state, materials, enrolment or AI actions.
CATALOG += [
    {'id':identifier,'title':title,'professional':[professional],'availability':'upcoming'}
    for identifier,title,professional in [
        ('education','教学设计实训','教育学'),
        ('design','数字产品设计实训','设计'),
        ('marketing','品牌营销策划实训','市场营销'),
        ('tourism','文旅推广实训','旅游管理'),
        ('languages','跨文化沟通实训','外语'),
        ('accounting','财务分析实训','会计学'),
        ('electronics','智能硬件应用实训','电子信息'),
        ('journalism','新媒体内容策划实训','新闻传播'),
    ]
]

def mount_projects(app,store,student,founder,user,root):
    executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='engineering-check')
    queued=set();queue_lock=threading.Lock()
    def load(uid):return store.load_project(uid,course.PROJECT,course.initial_state)
    def save(uid,state):store.save_project(uid,course.PROJECT,state);return course.response(state)
    def require(ok,message):
        if not ok:raise HTTPException(409,message)
    def text(payload,key,minimum=1):
        value=payload.get(key,'')
        if not isinstance(value,str) or not minimum<=len(value.strip())<=12000:raise HTTPException(422,f'{key}须为{minimum}—12000字。')
        return value
    def public_state(state):
        result=course.response(state)
        result['submissions']=[{k:v for k,v in s.items() if k!='archive_path'} for s in state['submissions']]
        return result
    def invalidate(state):
        if state['report'] or state['defense']:state['work_history'].append({k:copy.deepcopy(state[k]) for k in ('grade','report','report_review','defense','defense_review','defense_hash','posttest')})
        state.update(grade=None,report='',report_review=None,defense=[],defense_review=None,defense_hash=None,posttest=None,portfolio_note='')

    @app.get('/api/projects')
    def catalog(current=Depends(user)):
        projects=[]
        for item in CATALOG:
            progress=None
            if item['id']=='retail':progress=retail_progress(store.load(current['id']))
            elif item['id']==course.PROJECT:progress=course.progress(load(current['id']))
            projects.append({**item,'progress':progress})
        return {'projects':projects}

    @app.get('/api/projects/software-engineering')
    def state(current=Depends(student)):return {'meta':course.public_meta(),'state':public_state(load(current['id'])),'runtime':runner.runtime_status(),'mode':'ai' if app.state.model_config.enabled else 'basic'}

    @app.post('/api/projects/software-engineering/enroll')
    def enroll(current=Depends(student)):
        with store.user_lock(current['id']):return public_state_after_save(current['id'],load(current['id']))

    def public_state_after_save(uid,state):save(uid,state);return public_state(state)

    @app.get('/api/projects/software-engineering/starter')
    def starter(current=Depends(student)):
        file=runner.COURSE_DIR/'starter.zip'
        if not file.exists():raise HTTPException(503,'基础源码包尚未生成，请运行scripts/make_engineering_materials.py。')
        return FileResponse(file,media_type='application/zip',filename='activity-training-starter.zip')

    @app.post('/api/projects/software-engineering/diagnostic')
    def diagnostic(payload:dict,current=Depends(student)):
        with store.user_lock(current['id']):
            s=load(current['id']);require(not s['diagnostic'],'首次诊断已保存。')
            try:s['diagnostic']=course.quiz_grade(payload.get('answers'))
            except ValueError as e:raise HTTPException(422,str(e))
            s['next_task']=course.STAGES[1];return public_state_after_save(current['id'],s)

    @app.post('/api/projects/software-engineering/material/{kind}')
    def material(kind:str,payload:dict,current=Depends(student)):
        if kind not in ('requirements','reproduction','report','portfolio_note'):raise HTTPException(404,'材料类型不存在。')
        value=text(payload,'text',30 if kind!='portfolio_note' else 1)
        with store.user_lock(current['id']):
            s=load(current['id']);require(s['diagnostic'],'请先完成起点诊断。')
            if kind in ('requirements','reproduction','report'):require(not s['transfer'] and not any(j['kind']=='B' and j['status'] in ('queued','running') for j in s['jobs']),'需求B计分进行中或已冻结，不改写已计分的上游作品。')
            if kind=='reproduction':require(s['requirements'],'请先提交需求说明。')
            if kind=='report':require((s['grade'] or {}).get('passed'),'请先通过60分客观核验。');s['report_review']=None;s['defense']=[];s['defense_review']=None;s['posttest']=None
            if kind=='portfolio_note':require(s['transfer'],'请先提交需求变更测评。')
            s[kind]=value;s['next_task']=course.STAGES[course.progress(s)['stage']];return public_state_after_save(current['id'],s)

    @app.post('/api/projects/software-engineering/submission/{kind}')
    def submit(kind:str,file:UploadFile=File(...),current=Depends(student)):
        if kind not in ('A','B'):raise HTTPException(422,'提交类型须为A或B。')
        with store.user_lock(current['id']):
            s=load(current['id']);require(s['diagnostic'] and s['requirements'] and s['reproduction'],'请先完成诊断、需求和故障复现说明。')
            require(not s['transfer'],'计分版本已经冻结；继续练习请下载作品到本地，不改写原测评。')
            require(not any(j['kind']=='B' and j['status'] in ('queued','running') for j in s['jobs']),'需求B计分进行中，不能替换计分源码。')
            if kind=='B':require(course.progress(s)['completed'][5],'请先完成工程报告、三题答辩和后测。')
            identifier=secrets.token_hex(10);folder=root/'engineering'/current['id']/identifier
            try:digest,files=runner.archive(file.file.read(5*1024*1024+1),folder)
            except ValueError as e:
                if folder.exists():shutil.rmtree(folder)
                raise HTTPException(422,str(e))
            previous=course.latest_submission(s,kind)
            if previous and previous['hash']==digest:
                shutil.rmtree(folder);return public_state(s)
            if kind=='A':invalidate(s)
            item={'id':identifier,'version':len(s['submissions'])+1,'kind':kind,'hash':digest,'files':files,'archive_path':str(folder),'description':Path(file.filename or 'source.zip').name,'created':time.time()}
            s['submissions'].append(item);return public_state_after_save(current['id'],s)

    @app.get('/api/projects/software-engineering/source/{submission_id}')
    def source(submission_id:str,path:str,start:int=1,end:int=160,current=Depends(student)):
        s=load(current['id']);item=next((i for i in s['submissions'] if i['id']==submission_id),None)
        try:
            result=runner.read_source(item,path,start,end)
            previous=next((i for i in reversed(s['submissions']) if item and i['kind']==item['kind'] and i['version']<item['version']),None)
            result['diff']=runner.diff(previous,item,path);return result
        except ValueError as e:raise HTTPException(422,str(e))

    def work(uid,submission,kind,jid):
        try:
            with store.user_lock(uid):
                s=load(uid);job=next((j for j in s['jobs'] if j['id']==jid),None)
                if not job:return
                job['status']='running';save(uid,s)
            result=runner.check_submission(submission,kind,jid)
            with store.user_lock(uid):
                s=load(uid);job=next((j for j in s['jobs'] if j['id']==jid),None)
                if not job:return
                job.update(result,finished=time.time())
                latest=course.latest_submission(s,kind)
                if result.get('grade') and latest and latest['hash']==submission['hash']:
                    if kind=='A':s['grade']=result['grade']
                    elif not s['transfer']:s['transfer']={'evaluation':result['grade'],'mode':job['mode'],'hash':submission['hash'],'created':time.time()}
                s['next_task']=course.STAGES[course.progress(s)['stage']];save(uid,s)
        except Exception:
            # Don't persist raw exception content that may contain private host paths.
            try:
                with store.user_lock(uid):
                    s=load(uid);job=next((j for j in s['jobs'] if j['id']==jid),None)
                    if job:job.update(status='environment_failed',message='运行任务中断，请检查隔离执行服务后重试。');save(uid,s)
            except Exception:pass
        finally:
            with queue_lock:queued.discard((uid,jid))

    @app.post('/api/projects/software-engineering/check/{kind}')
    def check(kind:str,current=Depends(student)):
        if kind not in ('A','B'):raise HTTPException(422,'无效检查类型。')
        with store.user_lock(current['id']):
            s=load(current['id']);item=course.latest_submission(s,kind);require(item,'请先上传对应源码ZIP。')
            if kind=='B':require(not s['transfer'],'需求B计分已经冻结，不重复计分。');require(course.progress(s)['completed'][5],'请先完成答辩和后测。')
            existing=next((j for j in reversed(s['jobs']) if j['hash']==item['hash'] and j['version']==item['version'] and j['kind']==kind and j['status'] in ('queued','running','completed')),None)
            if existing:return existing
            status=runner.runtime_status()
            if not status['available']:raise HTTPException(503,status['reason'])
            if any(j['status'] in ('queued','running') for j in s['jobs']):raise HTTPException(409,'已有检查进行中，请等待完成。')
            job={'id':secrets.token_hex(8),'hash':item['hash'],'version':item['version'],'kind':kind,'status':'queued','created':time.time(),'mode':s['b_mode'] if kind=='B' else 'training'}
            s['jobs'].append(job);save(current['id'],s)
            with queue_lock:queued.add((current['id'],job['id']))
            executor.submit(work,current['id'],copy.deepcopy(item),kind,job['id']);return job

    @app.get('/api/projects/software-engineering/jobs/{jid}')
    def job(jid:str,current=Depends(student)):
        with store.user_lock(current['id']):
            s=load(current['id']);j=next((j for j in s['jobs'] if j['id']==jid),None)
            if not j:raise HTTPException(404,'检查不存在。')
            with queue_lock:alive=(current['id'],jid) in queued
            if j['status'] in ('queued','running') and not alive:j.update(status='environment_failed',message='服务重启导致任务中断，请重新检查。');save(current['id'],s)
            return {'job':j,'state':public_state(s)}

    @app.post('/api/projects/software-engineering/collaboration')
    def collaboration(current=Depends(student)):
        with store.user_lock(current['id']):
            s=load(current['id']);require(course.progress(s)['stage']==6 and not s['transfer'],'仅在未冻结的需求B测评中切换。')
            require(not any(j['kind']=='B' and j['status'] in ('queued','running') for j in s['jobs']),'检查进行中，协助模式已固定。')
            if s['b_mode']!='assisted':s['b_mode']='assisted';s['b_mode_history'].append({'mode':'assisted','created':time.time()})
            return public_state_after_save(current['id'],s)

    @app.post('/api/projects/software-engineering/defense/start')
    def defense_start(current=Depends(student)):
        with store.user_lock(current['id']):
            s=load(current['id']);require(s['report'] and (s['grade'] or {}).get('passed'),'请先提交有效工程报告。')
            if not s['defense']:s['defense']=[{'question':q,'answer':'','source':'basic'} for q in course.QUESTIONS];s['defense_hash']=course.latest_submission(s)['hash']
            return public_state_after_save(current['id'],s)

    @app.post('/api/projects/software-engineering/defense/answer')
    def defense_answer(payload:dict,current=Depends(student)):
        answer=text(payload,'answer');index=payload.get('index')
        with store.user_lock(current['id']):
            s=load(current['id']);require(type(index)is int and 0<=index<len(s['defense']),'请先开始答辩。');require(s['defense_hash']==course.latest_submission(s)['hash'],'代码已变更，请重新答辩。')
            require(not s['transfer'] and not any(j['kind']=='B' and j['status'] in ('queued','running') for j in s['jobs']),'需求B计分进行中或已冻结，原答辩不再改写。')
            s['defense'][index]['answer']=answer;s['defense_review']=None;return public_state_after_save(current['id'],s)

    @app.post('/api/projects/software-engineering/posttest')
    def posttest(payload:dict,current=Depends(student)):
        with store.user_lock(current['id']):
            s=load(current['id']);require(len(s['defense'])>=3 and all(t['answer'] for t in s['defense'][:3]),'请先完成三题答辩。');require(not s['posttest'],'后测已经完成。')
            try:s['posttest']=course.quiz_grade(payload.get('answers'),True)
            except ValueError as e:raise HTTPException(422,str(e))
            return public_state_after_save(current['id'],s)

    @app.post('/api/projects/software-engineering/coach')
    def coach(payload:dict,current=Depends(student)):
        purpose=payload.get('purpose')
        if purpose not in ('engineering_diagnosis','requirements','engineering_feedback','engineering_report','engineering_defense','engineering_portfolio'):raise HTTPException(422,'未知教练任务。')
        with store.user_lock(current['id']):
            original=load(current['id']);draft=copy.deepcopy(original)
            require(original['diagnostic'],'请先完成诊断。')
            if purpose=='requirements':require(original['requirements'],'请先提交需求。')
            if purpose=='engineering_report':require(original['report'],'请先提交工程报告。')
            if purpose=='engineering_defense':require(original['defense'],'请先开始答辩。')
            if purpose=='engineering_portfolio':require(original['transfer'],'请先完成需求变更测评。')
            if course.progress(original)['stage']==6 and original['b_mode']=='independent' and purpose=='engineering_feedback':raise HTTPException(409,'独立需求变更中请使用通用答疑，或开启AI协作。')
            learning_draft=store.load_learning(current['id'],course.PROJECT)
            context=learning.adaptive_context(learning_draft,course.PROJECT,draft,context_for(draft,purpose));result=run_agent(purpose,context,app.state.model_config,tools_for(draft,purpose,context,lambda args:learning.legacy_assignment(learning_draft,course.PROJECT,draft,args)))
            target=draft if result['status']=='ok' else original
            if result['status']=='ok':store.save_learning(current['id'],course.PROJECT,learning_draft)
            result.update(id=secrets.token_hex(8),purpose=purpose,created=time.time(),actions_committed=result['status']=='ok' and result['mode']=='ai')
            if result['mode']=='ai':target['agent_runs'].append(result)
            if result['needs_human_review']:target['human_reviews'].append({'id':secrets.token_hex(6),'status':'pending','reason':result['message'],'created':time.time()})
            save(current['id'],target);return {'run':result,'state':public_state(target)}

    @app.post('/api/projects/software-engineering/practice/{pid}')
    def practice(pid:str,payload:dict,current=Depends(student)):
        with store.user_lock(current['id']):
            s=load(current['id']);p=next((r for r in s['remediation'] if r['id']==pid),None)
            if not p:raise HTTPException(404,'补练不存在。')
            if p.get('adaptive'):raise HTTPException(409,'这是新变式练习，请在“我的针对性练习”中作答。')
            answer=payload.get('answer','')
            if not isinstance(answer,str) or len(answer)>200:raise HTTPException(422,'答案过长。')
            p['attempts']+=1;p['completed']=answer.strip()==course.CARDS[p['skill_id']]['answer'];p['hint_level']=min(3,p['hint_level']+1) if not p['completed'] else p['hint_level'];return public_state_after_save(current['id'],s)

    @app.post('/api/projects/software-engineering/preview/{kind}')
    def preview(kind:str,current=Depends(student)):
        if kind not in ('A','B'):raise HTTPException(422,'无效类型。')
        s=load(current['id']);item=course.latest_submission(s,kind);require(item,'请先上传源码。')
        try:return runner.start_preview(current['id'],item)
        except (ValueError,OSError) as e:raise HTTPException(503,str(e))

    @app.get('/api/projects/software-engineering/export/{format}')
    def export(format:str,kind:str='A',current=Depends(student)):
        s=load(current['id'])
        if format=='zip':
            item=course.latest_submission(s,kind);require(item,'没有对应源码。');buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
                for name in item['files']:z.write(Path(item['archive_path'])/name,name)
            return Response(buffer.getvalue(),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="my-engineering-{kind}.zip"'})
        if format not in ('json','md','html'):raise HTTPException(404,'格式不存在。')
        content=json.dumps(course.portfolio(s,True),ensure_ascii=False,indent=2) if format=='json' else course.export_markdown(s) if format=='md' else course.export_html(s)
        return Response(content,media_type={'json':'application/json','md':'text/markdown','html':'text/html'}[format],headers={'Content-Disposition':f'attachment; filename="engineering-portfolio.{format}"'})

    @app.post('/api/projects/software-engineering/share')
    def share(payload:dict,current=Depends(student)):
        if any(type(payload.get(k,False))is not bool for k in ('include_defense','include_reviews')):raise HTTPException(422,'分享选项须为开关。')
        return {'token':store.create_share(current['id'],course.portfolio(load(current['id']),include_defense=payload.get('include_defense',False),include_reviews=payload.get('include_reviews',False)))}

    @app.get('/api/operator/projects')
    def operator_projects(current=Depends(founder)):
        learners=[]
        for u in store.list_users():
            if u['role']!='student':continue
            s=load(u['id'])
            if not s['diagnostic'] and not s['submissions']:continue
            runs=s['agent_runs'];learners.append({'id':u['id'],'username':u['username'],'is_demo':bool(u['is_demo']),'project_id':course.PROJECT,'progress':course.progress(s),'objective_score':(s['grade'] or {}).get('score',0),'report_review':s['report_review'],'defense_review':s['defense_review'],'transfer':s['transfer'],'ai_runs':len(runs),'human_minutes':sum(r.get('minutes',0) for r in s['human_reviews']),'known_cost':sum(r.get('cost') or 0 for r in runs),'unpriced_runs':sum(r.get('cost') is None for r in runs),'pending_reviews':[r for r in s['human_reviews'] if r['status']=='pending']})
        return {'learners':learners,'currency':app.state.model_config.currency}

    @app.get('/api/operator/projects/software-engineering/learners/{uid}')
    def operator_work(uid:str,current=Depends(founder)):
        if not any(u['id']==uid and u['role']=='student' for u in store.list_users()):raise HTTPException(404,'学员不存在。')
        return public_state(load(uid))

    @app.post('/api/operator/projects/software-engineering/review')
    def operator_review(payload:dict,current=Depends(founder)):
        uid=payload.get('user_id');minutes=payload.get('minutes',0);note=text(payload,'note')
        if not any(u['id']==uid and u['role']=='student' for u in store.list_users()):raise HTTPException(404,'学员不存在。')
        if type(minutes)is not int or not 0<=minutes<=600:raise HTTPException(422,'时间须为0—600分钟。')
        with store.user_lock(uid):
            s=load(uid)
            for name,maximum in (('report_review',25),('defense_review',15)):
                if name in payload:
                    require(s['report'] and (s['grade'] or {}).get('passed'),'需要当前有效工程报告。')
                    if name=='defense_review':require(len(s['defense'])>=3 and all(t['answer'] for t in s['defense'][:3]),'需要完成三题答辩。')
                    score=payload[name]
                    if type(score)is not int or not 0<=score<=maximum:raise HTTPException(422,'分数超出量表。')
                    s[name]={'score':score,'max_score':maximum,'source':'human','reason':note,'previous':s[name],'created':time.time()}
            for r in s['human_reviews']:
                if r['status']=='pending':r['status']='resolved'
            s['human_reviews'].append({'id':secrets.token_hex(6),'status':'resolved','note':note,'minutes':minutes,'created':time.time()});save(uid,s);return {'ok':True}
