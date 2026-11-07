"""Teacher and student classroom workflows, with class-scoped authorization."""
import copy
import re
import threading
import time
from fastapi import Depends,HTTPException
from .classroom import ClassroomStore
from . import teaching,learning,engineering_course as engineering,course
from .agent import run_agent
from .engineering_runner import read_source


def mount_teacher(app,store,user,student):
    classes=ClassroomStore(store);app.state.classrooms=classes
    join_attempts={};join_lock=threading.Lock()

    def teacher(current=Depends(user)):
        if current['role']!='teacher':raise HTTPException(403,'此功能仅供教师使用。')
        return current

    def owned(cid,current):
        c=classes.get(cid)
        if not c or c['teacher_id']!=current['id']:raise HTTPException(404,'班级不存在或不属于你。')
        return c

    def learner(cid,uid,current):
        c=owned(cid,current);m=classes.member(cid,uid)
        if not m:raise HTTPException(404,'该学生不在此班级中。')
        return c,m

    def public_class(c,private=False):
        keys=['id','name','teacher_name','join_enabled','revision']
        if private:keys+=['join_code']
        return {k:c[k] for k in keys}

    def project(value):
        if not isinstance(value,str) or value not in teaching.PROJECTS:raise HTTPException(422,'请选择要查看或指导的实训项目；班级不限制学生选择项目。')
        return value

    def labeled(record):
        return {**record,'project_title':teaching.PROJECTS.get(record.get('project_id'),'原项目未标明')}

    def name(payload):
        value=payload.get('name')
        if not isinstance(value,str) or not 1<=len(value.strip())<=80:raise HTTPException(422,'班级名称须为1—80字。')
        return value.strip()

    def code(payload,current):
        with join_lock:
            now=time.monotonic();recent=[t for t in join_attempts.get(current['id'],[]) if now-t<60]
            if len(recent)>=12:raise HTTPException(429,'班级码尝试过多，请一分钟后再试。')
            if len(join_attempts)>1024:join_attempts.clear()
            join_attempts[current['id']]=recent+[now]
        value=payload.get('code')
        if not isinstance(value,str) or not re.fullmatch('[A-Fa-f0-9]{10}',value.strip()):raise HTTPException(422,'请填写老师提供的10位班级码。')
        return value.strip().upper()

    def may_teach(state,pid):
        if not state['diagnostic']:raise HTTPException(409,'学生尚未完成起点诊断，请先让学生完成诊断。')
        if learning.independent(pid,state):raise HTTPException(409,'当前为独立测评，暂不安排针对答案的补练或修改评价。请等待测评结束。')

    def proposal(cid,uid,rid):
        p=next((p for p in classes.rows('teaching_proposals',cid,uid) if p['id']==rid),None)
        if not p:raise HTTPException(404,'补练草案不存在。')
        return p

    @app.get('/api/teacher/classes')
    def list_classes(current=Depends(teacher)):
        return {'classes':[{**public_class(c,True),'member_count':len(classes.members(c['id']))} for c in classes.owned(current['id'])],
                'projects':teaching.PROJECTS,'mode':'ai' if app.state.model_config.enabled else 'basic'}

    @app.post('/api/teacher/classes')
    def create(payload:dict,current=Depends(teacher)):
        with store.user_lock('teacher:'+current['id']):
            if len(classes.owned(current['id']))>=100:raise HTTPException(409,'已达100个班级上限。')
            return public_class(classes.create(current['id'],name(payload)),True)

    @app.post('/api/teacher/classes/{cid}/settings')
    def settings(cid:str,payload:dict,current=Depends(teacher)):
        enabled=payload.get('join_enabled');rotate=payload.get('rotate_code',False)
        if type(enabled)is not bool or type(rotate)is not bool:raise HTTPException(422,'请选择是否允许加入及是否更换班级码。')
        with store.user_lock('class:'+cid):
            owned(cid,current);return public_class(classes.update(cid,name(payload),enabled,rotate),True)

    @app.get('/api/teacher/classes/{cid}')
    def dashboard(cid:str,project_id:str,include_demo:bool=False,current=Depends(teacher)):
        pid=project(project_id)
        with store.user_lock('class:'+cid):
            c=owned(cid,current);data=teaching.class_snapshot(store,classes,c,pid,include_demo)
            runs=[labeled(r) for r in classes.project_rows('teaching_runs',cid,pid)]
            return {'class':public_class(c,True),**data,'runs':runs[:50],
                    'insights':[{**r,'stale':r.get('fingerprint')!=data['fingerprint']} for r in runs if r.get('purpose')=='teacher_class' and r.get('insights')][:10],
                    'mode':'ai' if app.state.model_config.enabled else 'basic'}

    @app.post('/api/teacher/classes/{cid}/members/{uid}/remove')
    def remove(cid:str,uid:str,current=Depends(teacher)):
        with store.user_lock('class:'+cid):learner(cid,uid,current);classes.leave(cid,uid)
        return {'ok':True}

    @app.get('/api/student/classes')
    def my_classes(current=Depends(student)):
        return {'classes':[{**public_class(c),'notes':[labeled(r) for r in classes.rows('teaching_notes',c['id'],current['id'])[:20]]} for c in classes.joined(current['id'])]}

    @app.post('/api/student/classes/preview')
    def preview(payload:dict,current=Depends(student)):
        c=classes.by_code(code(payload,current))
        if not c:raise HTTPException(404,'班级码无效或老师已关闭加入。')
        return public_class(c)

    @app.post('/api/student/classes/join')
    def join(payload:dict,current=Depends(student)):
        if payload.get('consent') is not True:raise HTTPException(422,'请先确认加入后教师可查看各实训项目的公开学习记录。')
        value=code(payload,current);c=classes.by_code(value)
        if not c:raise HTTPException(404,'班级码无效或老师已关闭加入。')
        with store.user_lock('class:'+c['id']):
            c=classes.by_code(value)
            if not c:raise HTTPException(409,'班级码已变化，请重新确认。')
            if len(classes.members(c['id']))>=300 and not classes.member(c['id'],current['id']):raise HTTPException(409,'本班已达300人上限。')
            classes.join(c['id'],current['id']);return public_class(c)

    @app.post('/api/student/classes/{cid}/leave')
    def leave(cid:str,current=Depends(student)):
        with store.user_lock('class:'+cid):
            if not classes.member(cid,current['id']):raise HTTPException(404,'你尚未加入此班。')
            classes.leave(cid,current['id'])
        return {'ok':True}

    @app.get('/api/teacher/classes/{cid}/learners/{uid}')
    def work(cid:str,uid:str,project_id:str,current=Depends(teacher)):
        pid=project(project_id)
        with store.user_lock('class:'+cid),store.user_lock(uid):
            c,m=learner(cid,uid,current)
            s=teaching.snapshot(store,uid,pid)
            return {'learner':m,'class':public_class(c),**s,'teaching_evidence':teaching.plan_context(s,pid)['facts'],
                    'proposals':classes.project_rows('teaching_proposals',cid,pid,uid)[:30],'notes':classes.project_rows('teaching_notes',cid,pid,uid)[:50]}

    @app.get('/api/teacher/classes/{cid}/learners/{uid}/source')
    def source(cid:str,uid:str,project_id:str,path:str,expected_hash:str,start:int=1,current=Depends(teacher)):
        pid=project(project_id)
        with store.user_lock('class:'+cid),store.user_lock(uid):
            c,_=learner(cid,uid,current)
            if pid!=engineering.PROJECT:raise HTTPException(404,'此项目没有源码。')
            state=store.load_project(uid,pid,engineering.initial_state)
            item=engineering.latest_submission(state)
            if not item or item['hash']!=expected_hash:raise HTTPException(409,'源码版本已改变，请重新读取学生作品后查看源码。')
            try:return read_source(item,path,start,start+199)
            except (ValueError,OSError,UnicodeError):raise HTTPException(422,'只能读取当前A版本中的有效源文件，每次最多200行。')

    def begin_run(c,current,purpose,signature,pid):
        now=time.time()
        if any(r.get('status')=='running' and now-r['created']<360 for r in classes.rows('teaching_runs',c['id'])):raise HTTPException(409,'本班已有AI请求正在处理，请等待完成，不会重复调用。')
        row={'project_id':pid,'status':'running','purpose':purpose,'teacher_id':current['id'],'fingerprint':signature,'message':'正在读取教学证据…','cost':None}
        return classes.put('teaching_runs',c['id'],row)

    @app.post('/api/teacher/classes/{cid}/learners/{uid}/plan')
    def plan(cid:str,uid:str,payload:dict,current=Depends(teacher)):
        pid=project(payload.get('project_id'))
        use_ai=payload.get('use_ai',True)
        if type(use_ai)is not bool:raise HTTPException(422,'请选择AI草案或手动草案。')
        with store.user_lock('class:'+cid),store.user_lock(uid):
            c,_=learner(cid,uid,current);state=store.load_project(uid,pid,engineering.initial_state);may_teach(state,pid)
            s=teaching.snapshot(store,uid,pid);context=teaching.plan_context(s,pid);class_revision=c['revision']
            if payload.get('fingerprint')!=s['fingerprint']:raise HTTPException(409,'学生记录已变化，请重新读取后再提出草案。')
            if not use_ai:
                try:body=teaching.validate_plan(payload,context,pid)
                except ValueError as e:raise HTTPException(422,str(e))
                rid=classes.put('teaching_proposals',cid,{'project_id':pid,'status':'draft','source':'teacher','fingerprint':s['fingerprint'],'class_revision':class_revision,'source_version':s['source_version'],'body':body},uid)
                return {'proposal_id':rid,'message':'手动草案已保存，请查看并确认后发给学生。'}
            if not app.state.model_config.enabled:raise HTTPException(409,'AI尚未接通；可以选择手动建立补练草案。')
            run_id=begin_run(c,current,'teacher_plan',s['fingerprint'],pid)
        drafts=[];result=run_agent('teacher_plan',context,app.state.model_config,{'save_teaching_proposal':teaching.plan_tool(context,pid,drafts)})
        if result['status']=='ok' and not drafts:result.update(status='no_action',message='AI没有保存有效草案；请重试或手动安排。')
        with store.user_lock('class:'+cid),store.user_lock(uid):
            fresh_class=owned(cid,current);member=classes.member(cid,uid)
            fresh=bool(member) and fresh_class['revision']==class_revision and teaching.snapshot(store,uid,pid)['fingerprint']==s['fingerprint']
            if not fresh:result.update(status='stale',message='班级或学生学习记录已改变，旧草案未应用，请重新读取学生后再安排。')
            result.update(project_id=pid,purpose='teacher_plan',fingerprint=s['fingerprint'],teacher_id=current['id'],actions_committed=False)
            rid=None
            if result['status']=='ok':
                rid=classes.put('teaching_proposals',cid,{'project_id':pid,'status':'draft','source':'ai','fingerprint':s['fingerprint'],'class_revision':class_revision,'source_version':s['source_version'],'body':drafts[0],'run_id':run_id},uid)
                result['message']='AI草案已保存，尚未发题。请检查证据、调整内容，再确认发送。'
            classes.put('teaching_runs',cid,result,record_id=run_id)
            return {'run':result,'proposal_id':rid}

    @app.post('/api/teacher/classes/{cid}/learners/{uid}/proposals/{rid}/decision')
    def decide(cid:str,uid:str,rid:str,payload:dict,current=Depends(teacher)):
        pid=project(payload.get('project_id'))
        action=payload.get('action')
        if action not in ('approve','reject'):raise HTTPException(422,'请选择确认发送或拒绝草案。')
        with store.user_lock('class:'+cid),store.user_lock(uid):
            c,_=learner(cid,uid,current);p=proposal(cid,uid,rid)
            if p.get('project_id')!=pid:raise HTTPException(409,'这份草案属于另一实训项目，请切换到原项目后处理。')
            if p['status']!='draft':raise HTTPException(409,'这份草案已处理，请重新读取。')
            if action=='reject':p['status']='rejected';classes.put('teaching_proposals',cid,p,uid,rid);return {'message':'草案已拒绝，未修改学生练习。'}
            state=store.load_project(uid,pid,engineering.initial_state);may_teach(state,pid);s=teaching.snapshot(store,uid,pid)
            if s['fingerprint']!=p['fingerprint'] or c['revision']!=p.get('class_revision'):
                p['status']='stale';classes.put('teaching_proposals',cid,p,uid,rid);raise HTTPException(409,'学生记录已变化，草案已过期，请重新提出草案。')
            try:body=teaching.validate_plan(payload.get('body',{}),teaching.plan_context(s,pid),pid)
            except (ValueError,AttributeError) as e:raise HTTPException(422,str(e))
            memory=store.load_learning(uid,pid)
            if any(e['status']=='active' and e['skill_id']==body['skill_id'] and e['source_version']==s['source_version'] for e in memory['exercises']):raise HTTPException(409,'学生已有同技能未完成练习，请先让学生完成旧题；不会覆盖已有作答。')
            try:exercise=learning.create_exercise(memory,pid,{**body,'source':'teacher'},s['source_version'])
            except ValueError as e:raise HTTPException(409,str(e))
            private=learning.find_exercise(memory,exercise['id']);private.update(teacher_message=body['teacher_message'],teacher_name=current['username'],class_name=c['name'])
            p.update(status='applied',body=body,exercise_id=exercise['id'],decided=time.time())
            note={'type':'assignment','text':body['teacher_message'],'reason':body['reason'],'source_version':s['source_version'],'teacher_name':current['username'],'exercise_id':exercise['id']}
            classes.commit(cid,uid,pid,state,note,memory,(rid,p))
            return {'message':'已发送教师补练。学生重新打开本项目后，可在「我的针对性练习」中作答。'}

    @app.post('/api/teacher/classes/{cid}/learners/{uid}/review')
    def review(cid:str,uid:str,payload:dict,current=Depends(teacher)):
        pid=project(payload.get('project_id'))
        text=payload.get('note');minutes=payload.get('minutes',0)
        resolve_ids=payload.get('resolve_ids',[])
        if not isinstance(resolve_ids,list) or len(resolve_ids)>100 or any(not isinstance(r,str) for r in resolve_ids) or len(set(resolve_ids))!=len(resolve_ids):raise HTTPException(422,'请逐项选择有效的待复核请求。')
        if not isinstance(text,str) or not 1<=len(text.strip())<=2000 or type(minutes)is not int or not 0<=minutes<=600:raise HTTPException(422,'请填写1—2000字意见及0—600分钟人工时间。')
        for key,maximum in (('report_review',25),('defense_review',15)):
            if key in payload and (type(payload[key])is not int or not 0<=payload[key]<=maximum):raise HTTPException(422,'报告分数须0—25整数，答辩须0—15整数。')
        with store.user_lock('class:'+cid),store.user_lock(uid):
            c,_=learner(cid,uid,current);state=store.load_project(uid,pid,engineering.initial_state);s=teaching.snapshot(store,uid,pid)
            if payload.get('fingerprint')!=s['fingerprint']:raise HTTPException(409,'学生记录已变化，请重新读取作品后复核。')
            if learning.independent(pid,state):raise HTTPException(409,'独立测评正在进行，请在结束后再留言或复核。')
            pending={r['id'] for r in state['human_reviews'] if r['status']=='pending'}
            if any(r not in pending for r in resolve_ids):raise HTTPException(409,'所选请求已处理或不存在，请重新读取后选择。')
            grading=any(k in payload for k in ('report_review','defense_review'))
            if grading:
                valid=bool(state['report']) and (not state['report_stale'] if pid=='retail' else bool((state['grade'] or {}).get('passed')))
                if not valid:raise HTTPException(409,'需要当前有效报告和核验结果才能评分。')
            if 'defense_review' in payload:
                answered=state['defense'][:3] if pid!= 'retail' else [t for t in state['defense'] if t.get('answer')]
                if len(answered)<3 or any(not t.get('answer') for t in answered):raise HTTPException(409,'请先完成至少三题答辩。')
            audit={'project_id':pid,'id':str(time.time_ns()),'status':'resolved','note':text.strip(),'minutes':minutes,'created':time.time(),'source':'teacher','teacher_id':current['id'],'teacher_name':current['username'],'class_id':cid,'source_version':s['source_version'],'resolved_request_ids':resolve_ids,'previous_reviews':{k:copy.deepcopy(state[k]) for k in ('report_review','defense_review') if k in payload}}
            for key,maximum in (('report_review',25),('defense_review',15)):
                if key in payload:state[key]={'previous':state[key],'score':payload[key],'max_score':maximum,'source':'human','reason':text.strip(),'teacher_name':current['username'],'created':time.time(),**({'hash':(engineering.latest_submission(state) or {}).get('hash')} if pid!= 'retail' else {})}
            for old in state['human_reviews']:
                if old['id'] in resolve_ids:old.update(status='resolved',resolved_by=audit['id'])
            state['human_reviews'].append(audit)
            classes.commit(cid,uid,pid,state,{'type':'review','text':text.strip(),'minutes':minutes,'source_version':s['source_version'],'teacher_name':current['username'],'scores':{k:payload[k] for k in ('report_review','defense_review') if k in payload}})
            return {'message':'教师复核已保存，原评价和修改理由均已保留。'}

    @app.post('/api/teacher/classes/{cid}/insights')
    def insights(cid:str,payload:dict,current=Depends(teacher)):
        pid=project(payload.get('project_id'))
        include_demo=payload.get('include_demo',False)
        if type(include_demo)is not bool:raise HTTPException(422,'请选择是否包含演示学生。')
        with store.user_lock('class:'+cid):
            c=owned(cid,current);data=teaching.class_snapshot(store,classes,c,pid,include_demo)
            if not data['summary']['included_students']:raise HTTPException(409,'没有可分析的学生。可以先邀请学生，或明确勾选包含演示学生。')
            if not app.state.model_config.enabled:raise HTTPException(409,'AI尚未接通，当前仍可查看程序计算的共性问题统计。')
            context=teaching.insights_context(data,pid);rid=begin_run(c,current,'teacher_class',data['fingerprint'],pid)
        drafts=[];result=run_agent('teacher_class',context,app.state.model_config,{'save_class_insights':teaching.insights_tool(context,pid,drafts)})
        if result['status']=='ok' and not drafts:result.update(status='no_action',message='AI未保存有效教學建议，请稍后重试。')
        with store.user_lock('class:'+cid):
            latest=owned(cid,current);fresh=teaching.class_snapshot(store,classes,latest,pid,include_demo)['fingerprint']==data['fingerprint']
            if not fresh:result.update(status='stale',message='班级资料已变化，本次建议已过期，请重新整理。')
            result.update(project_id=pid,purpose='teacher_class',fingerprint=data['fingerprint'],include_demo=include_demo,teacher_id=current['id'],actions_committed=False)
            if result['status']=='ok':result['insights']=drafts[0]
            classes.put('teaching_runs',cid,result,record_id=rid)
            return {'run':result}
