"""Evidence projections and validated teacher-only agent drafts."""
import copy
import hashlib
import json
import time
from . import course,engineering_course as engineering,learning,learning_templates as templates
from .portfolio import progress,objective_score

PROJECTS={'retail':'销售分析与运营建议','software-engineering':'软件工程：活动报名系统'}

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()

def fingerprint(state,memory,pid):return digest({'project_id':pid,'revision':state.get('revision',0),'version':learning.source_version(pid,state),'memory':memory})

def snapshot(store,uid,pid):
    state=store.load_project(uid,pid,engineering.initial_state);memory=store.load_learning(uid,pid)
    version=learning.source_version(pid,state);issues=learning.learning_evidence(pid,state,memory=memory)
    current=[learning.public_exercise(e) for e in memory['exercises'] if e['source_version']==version]
    p=progress(state) if pid=='retail' else engineering.progress(state)
    cards=course.CARDS if pid=='retail' else engineering.CARDS
    current_job=None
    if pid==engineering.PROJECT:
        item=engineering.latest_submission(state)
        job=next((j for j in reversed(state['jobs']) if item and j['kind']=='A' and j['hash']==item['hash'] and j['version']==item['version']),None)
        status=(job or {}).get('status')
        safe_messages={'queued':'检查已排队，尚无本次结果。','running':'检查正在运行，尚不能据此判断技能错误。','timeout':'检查超过时限，尚无本次有效核验。请学生查看运行状态或联系平台维护人员。','environment_failed':'运行环境未完成检查。请学生查看隔离执行服务状态，解决后重新检查。','completed':'本次检查已结束，可以核对实际结果。'}
        if job:current_job={**{k:job[k] for k in ('id','kind','hash','version','status','created','finished') if k in job},'message':safe_messages.get(status,'本次检查未完成，请重新读取运行状态。')}
        verification_status='not_submitted' if not item else 'pending' if status in ('queued','running') else status if status in ('timeout','environment_failed') else 'verified' if state.get('grade') else 'not_checked'
    else:
        present=sum(bool(g) for g in state['grades'].values())
        verification_status='verified' if present==3 else 'partial' if present else 'not_submitted'
    summary={'progress':p,'stage_name':(course.STAGES if pid=='retail' else engineering.STAGES)[p['stage']],
             'objective_score':objective_score(state) if pid=='retail' and verification_status!='not_submitted' else (state.get('grade') or {}).get('score') if verification_status=='verified' else None,
             'verification_status':verification_status,
             'failed_count':len(issues),'active_exercises':sum(e['status']=='active' for e in current),
             'passed_exercises':sum(e['status']=='passed' for e in current),'pending_reviews':sum(r['status']=='pending' for r in state['human_reviews']),
             'needs_resubmission':bool(issues) and any(e['status']=='passed' and e['skill_id'] in {i['skill_id'] for i in issues} for e in current),
             'independent':learning.independent(pid,state),'diagnosed':bool(state['diagnostic'])}
    # A deliberate whitelist: never send chats, answer keys or filesystem paths.
    work={k:copy.deepcopy(state[k]) for k in ('diagnostic','report','report_review','defense','defense_review','human_reviews','portfolio_note')}
    if pid=='retail':work.update(grades=state['grades'],metrics=state['metrics'],metric_titles=course.METRIC_LABELS,tables=state['tables'],report_stale=state['report_stale'])
    else:work.update(requirements=state['requirements'],reproduction=state['reproduction'],grade=state['grade'],posttest=state['posttest'],
                     checks_pending=verification_status=='pending',current_job=current_job)
    work['submissions']=[{k:s[k] for k in ('id','version','kind','created','hash','files','evaluation','description') if k in s} for s in state['submissions'] if s['kind']!='B']
    work['transfer']={'completed':True,'score':state['transfer']['evaluation']['score'],'max_score':state['transfer']['evaluation']['max_score']} if state['transfer'] else None
    return {'project_id':pid,'project_title':PROJECTS[pid],'summary':summary,'work':work,'issues':issues,'exercises':current,'skill_evidence':learning.skills(memory,version),
            'source_version':version,'fingerprint':fingerprint(state,memory,pid),'revision':state.get('revision',0),'as_of':time.time(),
            'titles':{k:v['title'] for k,v in cards.items()},'catalog':templates.catalog(pid),'ai_runs':len(state['agent_runs']),
            'agent_records':[{k:r[k] for k in ('id','created','purpose','status','message','evidence_ids','actions','actions_committed','usage','usage_complete','model','cost','currency','elapsed_ms') if k in r} for r in state['agent_runs'] if r.get('purpose') not in ('question','operator')][-30:],
            'platform_hints':sum(e.get('hint_level_used',0)>0 or bool(e.get('explanation')) for e in current),
            'policy':'平台内协助记录无法证明没有使用外部AI；模拟实训不代表真实工作经历。'}

def class_snapshot(store,classes,c,pid,include_demo=False):
    members=classes.members(c['id']);learners=[];topics={}
    for m in members:
        with store.user_lock(m['id']):s=snapshot(store,m['id'],pid)
        learners.append({**m,**s['summary'],'fingerprint':s['fingerprint']})
        if m['is_demo'] and not include_demo:continue
        for skill in set(i['skill_id'] for i in s['issues']):
            r=topics.setdefault(skill,{'skill_id':skill,'title':s['titles'][skill],'count':0,'evidence_id':'class:'+c['id']+':project:'+pid+':skill:'+skill,'examples':[]})
            r['count']+=1
            for issue in s['issues']:
                if issue['skill_id']==skill and issue['label'] not in r['examples']:r['examples'].append(issue['label'])
    considered=[l for l in learners if include_demo or not l['is_demo']]
    summary={'students':len(members),'included_students':len(considered),'excluded_demo':sum(bool(l['is_demo']) for l in learners) if not include_demo else 0,
             'finished':sum(l['progress']['finished'] for l in considered),'needs_support':sum(l['failed_count']>0 for l in considered),
             'active_exercises':sum(l['active_exercises'] for l in considered),'pending_reviews':sum(l['pending_reviews'] for l in considered),
             'pending_checks':sum(l['verification_status']=='pending' for l in considered),'execution_problems':sum(l['verification_status'] in ('timeout','environment_failed') for l in considered)}
    version=digest({'project_id':pid,'class_revision':c['revision'],'learners':[(l['id'],l['fingerprint']) for l in learners],'include_demo':include_demo})
    return {'project_id':pid,'project_title':PROJECTS[pid],'learners':learners,'topics':sorted(topics.values(),key=lambda t:-t['count']),'summary':summary,'fingerprint':version,'include_demo':include_demo,'as_of':time.time()}

def plan_context(s,pid):
    facts={i['evidence_id']:i for i in s['issues']}
    facts['teaching:progress']={**s['summary'],'source_version':s['source_version']}
    for e in s['exercises'][-12:]:facts['teaching:exercise:'+e['id']]=e
    return {'project_id':pid,'evidence_ids':list(facts),'facts':facts,'exercise_catalog':s['catalog'],
            'policy':'仅给教师提出待确认草案。不发布练习，不评分。未知错因保持待辨别，说明先向学生了解方法。不要输出当前题答案。'}

def validate_plan(body,context,pid):
    skill=body.get('skill_id');template=body.get('template_id');level=body.get('difficulty');catalog=templates.catalog(pid)
    if not isinstance(template,str) or template not in catalog or catalog[template]['skill_id']!=skill or type(level)is not int or not 1<=level<=3:raise ValueError('请选择有效的技能、匹配题型和1—3级难度。')
    for name,maximum in (('reason',2000),('teacher_message',2000)):
        if not isinstance(body.get(name),str) or not 1<=len(body[name].strip())<=maximum:raise ValueError('请填写安排理由及给学生的说明（各1—2000字）。')
    ids=body.get('evidence_ids')
    if not isinstance(ids,list) or not ids or len(ids)>30 or any(not isinstance(i,str) or i not in context['evidence_ids'] for i in ids):raise ValueError('草案必须引用当前实际存在的教学证据。')
    return {k:copy.deepcopy(body[k]) for k in ('skill_id','template_id','difficulty','reason','teacher_message','evidence_ids')}

def plan_tool(context,pid,drafts):
    def save(args):
        row=validate_plan(args,context,pid);drafts[:]=[row];return {'saved_as_draft':True,'evidence_ids':row['evidence_ids'],'instruction':'只有教师确认后才发给学生。'}
    return save

def insights_context(data,pid):
    facts={t['evidence_id']:{k:v for k,v in t.items() if k!='evidence_id'} for t in data['topics']}
    facts['class:summary']=data['summary']
    return {'project_id':pid,'facts':facts,'evidence_ids':list(facts),'policy':'按当前汇总建议讲解内容和行动。同一技能每个学生只计一次，人数不是错误次数。没有实际学生不得编造学习效果，未诊断不代表掌握，演示数据不代表真实试用。'}

def insights_tool(context,pid,drafts):
    def save(args):
        summary=args.get('summary');topics=args.get('topics')
        if not isinstance(summary,str) or not 1<=len(summary)<=4000 or not isinstance(topics,list) or len(topics)>12:raise ValueError('Invalid teaching insights')
        for t in topics:
            if not isinstance(t,dict) or t.get('skill_id') not in templates.KINDS[pid]:raise ValueError('Unknown skill')
            if any(not isinstance(t.get(k),str) or not 1<=len(t[k])<=2000 for k in ('reason','teaching_action')):raise ValueError('Missing teaching explanation')
            ids=t.get('evidence_ids')
            if not isinstance(ids,list) or not ids or any(not isinstance(i,str) or i not in context['evidence_ids'] for i in ids):raise ValueError('Invalid class evidence')
            if not any(context['facts'][i].get('skill_id')==t['skill_id'] for i in ids):raise ValueError('Missing evidence for this skill')
        drafts[:]=[{'summary':summary,'topics':copy.deepcopy(topics)}];return {'saved':True,'evidence_ids':context['evidence_ids']}
    return save
