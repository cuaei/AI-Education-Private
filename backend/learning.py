"""Private exercise state, evidence-based teaching actions and public projections."""
import math
import secrets
import time
from . import course, engineering_course as engineering, learning_templates as templates

PROMPT_VERSION='personalized-2026.10.12.2'
STATUS_NAMES={'insufficient':'证据不足','practice':'需练习','assisted':'协助下通过','independent':'平台内无提示新题通过'}

def initial_learning():return {'schema_version':1,'exercises':[],'events':[],'probes':{},'plans':[],'next_action':''}

def event(memory,action,**fields):
    row={'id':secrets.token_hex(8),'action':action,'created':time.time(),**fields};memory['events'].append(row);return row

def source_version(project,state,kind='A'):
    if project=='retail':return str(state['data_revision'])
    sub=engineering.latest_submission(state,kind)
    # Before source upload, bind diagnosis/material revisions, not transient requests.
    return f"{kind}:{sub['hash']}:{sub['version']}" if sub else f"{kind}:materials:{bool(state['diagnostic'])}:{bool(state['requirements'])}:{bool(state['reproduction'])}"

def independent(project,state):
    if project=='retail':
        from .portfolio import progress
        return progress(state)['stage']==6 and not state['transfer']
    return engineering.progress(state)['stage']==6 and state['b_mode']=='independent' and not state['transfer']

def learning_evidence(project,state,kind='A',memory=None):
    out=[];version=source_version(project,state,kind)
    if project=='retail':
        for group,grade in state['grades'].items():
            if not grade:continue
            for c in grade.get('checks',[]):
                if c['passed']:continue
                if c.get('verification_completed') is False or c.get('failure_type') in ('timeout','environment_failed') or '超时' in str(c.get('actual','')):continue
                d=next((d for d in grade.get('diagnoses',[]) if d['check_key']==c['key']),None)
                out.append({**(d or {}),'check_key':c['key'],'label':c['label'],'skill_id':d['skill_id'] if d else 'cleaning' if group=='clean' else 'chart' if group=='groups' else 'percentage_unit' if c['key'] in ('change_rate','refund_rate') else 'refund','status':d['status'] if d else 'insufficient','evidence_id':f'learning:{version}:{group}:{c["key"]}','source':'program','statement':'程序确认本项未通过；错误原因须依据步骤或复现，不能只凭分数推断。'})
    else:
        grade=state.get('grade') if kind=='A' else (state.get('transfer') or {}).get('evaluation')
        if grade:
            for c in grade.get('checks',[]):
                if c['passed']:continue
                if c.get('verification_completed') is False or c.get('failure_type') in ('timeout','environment_failed') or any(t in str(c.get('actual','')) for t in ('超时','环境不可用','尚未完成')):continue
                label=str(c.get('label',''));key=c['key']
                skill=c.get('skill')
                if skill not in engineering.CARDS:
                    skill='testing' if c.get('dimension')=='regression' else 'auth' if any(t in label for t in ('权限','归属','越权')) else 'transaction' if any(t in label for t in ('并发','容量','事务')) else 'state' if any(t in label for t in ('重复','取消','幂等')) else 'frontend' if c.get('dimension')=='frontend' else 'testing' if c.get('dimension')=='testing' else 'http'
                out.append({'check_key':key,'label':label,'skill_id':skill,'status':'insufficient','evidence_id':f'learning:{version}:check:{key}','source':'program','statement':'实际行为未通过；代码根因待阅读相关源码或复现确认。','actual':str(c.get('actual',''))[:600]})
    if not out and not state.get('transfer'):
        for skill in (state.get('diagnostic') or {}).get('weak_skills',[]):
            out.append({'check_key':'diagnostic:'+skill,'label':(course.CARDS if project=='retail' else engineering.CARDS)[skill]['title'],'skill_id':skill,'status':'insufficient','evidence_id':'learning:diagnostic:'+skill,'source':'diagnostic','statement':'首次测评该概念未通过；需要新题确认，不直接证明稳定能力。'})
    if memory:
        for probe in memory['probes'].values():
            if probe['source_version']==version and probe.get('answered'):
                for diagnosis in probe.get('diagnoses',[]):
                    original=next((i for i in out if i['check_key']==probe['check_key']==diagnosis['check_key']),None)
                    if original:original.update(diagnosis)
    return out

def public_exercise(item):
    keys=('id','project_id','template_id','template_version','skill_id','difficulty','question','options','answer_type','unit','source_version','evidence_ids','reason','source','created','status','hint_level_used','hints_shown','assisted','explanation','attempts','abandoned','purpose','teacher_message','teacher_name','class_name')
    return {k:item[k] for k in keys if k in item}

def skills(memory,version):
    rows={}
    for ex in memory['exercises']:
        if ex['source_version']!=version:continue
        skill=ex['skill_id'];r=rows.setdefault(skill,{'skill_id':skill,'status':'insufficient','independent_count':0,'independent_templates':[],'attempts':0,'passed_count':0})
        r['attempts']+=len(ex['attempts'])
        if not ex['attempts']:continue
        last=ex['attempts'][-1]
        if not last['passed']:r.update(status='practice',independent_count=0,independent_templates=[]);continue
        r['passed_count']+=1
        if ex['attempts'][0]['passed'] and not ex['assisted'] and ex['hint_level_used']==0:
            r['independent_count']+=1
            if ex['template_id'] not in r['independent_templates']:r['independent_templates'].append(ex['template_id'])
            r['status']='independent' if r['independent_count']>=2 and len(r['independent_templates'])>=2 else 'assisted' if r['status']=='assisted' else 'insufficient'
        else:r['status']='assisted'
    for r in rows.values():r['label']=STATUS_NAMES[r['status']]
    return list(rows.values())

def public_learning(memory,version):
    return {'schema_version':1,'source_version':version,'exercises':[public_exercise(e) for e in memory['exercises']],'skill_evidence':skills(memory,version),'probes':memory['probes'],'events':memory['events'][-100:],'next_action':memory['next_action']}

def create_exercise(memory,project,plan,version):
    skill=plan['skill_id'];template=plan['template_id'];difficulty=plan['difficulty'];catalog=templates.catalog(project)
    if template not in catalog or catalog[template]['skill_id']!=skill or type(difficulty)is not int or difficulty not in (1,2,3):raise ValueError('题型与技能或难度不匹配。')
    existing=next((x for x in reversed(memory['exercises']) if x['skill_id']==skill and x['source_version']==version and x['status']=='active'),None)
    if existing:return public_exercise(existing)
    if len(memory['exercises'])>=300:raise ValueError('已达300道练习上限，请联系人工复核。')
    for _ in range(100):
        item=templates.generate_exercise(project,template,difficulty,secrets.randbits(48))
        if not any(e['template_id']==template and e['question']==item['question'] and e['options']==item['options'] for e in memory['exercises']):break
    else:raise ValueError('该题型暂没有新的实例，请选择另一题型。')
    item.update(id=secrets.token_hex(10),project_id=project,source_version=version,evidence_ids=plan.get('evidence_ids',[]),reason=plan.get('reason','围绕当前技能安排新实例。'),source=plan.get('source','basic'),created=time.time(),status='active',hint_level_used=0,hints_shown=[],assisted=False,attempts=[],purpose=plan.get('purpose','practice'))
    memory['exercises'].append(item);event(memory,'exercise_created',exercise_id=item['id'],skill_id=skill,source_version=version,source=item['source'],template_id=template)
    memory['next_action']='完成新题，再回到原任务重新提交。';return public_exercise(item)

def find_exercise(memory,exercise_id):
    ex=next((e for e in memory['exercises'] if e['id']==exercise_id),None)
    if not ex:raise KeyError('练习不存在。')
    return ex

def grade_attempt(memory,exercise_id,answer,attempt_id):
    ex=find_exercise(memory,exercise_id)
    old=next((a for a in ex['attempts'] if a['attempt_id']==attempt_id),None)
    if old:return old
    if ex['status']!='active':raise ValueError('此题已完成或放弃，请做新题。')
    if len(ex['attempts'])>=10:raise ValueError('本题已尝试10次，请换一道新题或联系人工复核。')
    if ex['answer_type']=='number':
        try:
            if isinstance(answer,bool) or answer is None or not math.isfinite(float(answer)):raise ValueError()
            passed=abs(float(answer)-ex['expected_answer'])<=0.01000001
        except (ValueError,TypeError):raise ValueError('请输入有限数字。')
    else:
        if answer not in [o['id'] for o in ex['options']]:raise ValueError('请选择本题中的选项。')
        passed=answer==ex['expected_answer']
    row={'attempt_id':attempt_id,'answer':answer,'passed':passed,'hint_level_used':ex['hint_level_used'],'assisted':ex['assisted'],'created':time.time()};ex['attempts'].append(row)
    if passed:ex['status']='passed'
    event(memory,'attempt',exercise_id=exercise_id,skill_id=ex['skill_id'],source_version=ex['source_version'],passed=passed,assisted=ex['assisted'],hint_level_used=ex['hint_level_used'],first_attempt=len(ex['attempts'])==1)
    memory['next_action']='换一道新题，不看提示；再回到原任务重交。' if passed else '检查规则与步骤，可请求下一层提示或让AI解释。'
    return row

def reveal_hint(memory,exercise_id):
    ex=find_exercise(memory,exercise_id)
    if ex['status']!='active':raise ValueError('已结束的题不能继续请求提示。')
    level=min(3,ex['hint_level_used']+1);ex['hint_level_used']=level;ex['assisted']=True;ex['hints_shown']=ex['hints'][:level]
    event(memory,'hint',exercise_id=ex['id'],skill_id=ex['skill_id'],source_version=ex['source_version'],level=level);return public_exercise(ex)

def mark_assisted(memory,version,reason):
    for ex in memory['exercises']:
        if ex['source_version']==version and ex['status']=='active':
            ex['assisted']=True;event(memory,'assistance',exercise_id=ex['id'],skill_id=ex['skill_id'],source_version=version,reason=reason)

def adaptive_context(memory,project,state,base_context,exercise_id=None,kind='A'):
    version=source_version(project,state,kind);issues=learning_evidence(project,state,kind,memory)
    facts={**base_context.get('facts',{}),**{i['evidence_id']:i for i in issues}}
    if exercise_id:
        ex=find_exercise(memory,exercise_id);facts['exercise:'+ex['id']]=public_exercise(ex)
    catalog=templates.catalog(project)
    for key,probe in memory['probes'].items():
        if probe['source_version']==version and probe.get('answered'):
            facts['probe:'+key]={'answer':probe['answer'],'reported_steps':probe.get('reported_steps',{}),'diagnoses':probe.get('diagnoses',[]),'source':'student_report'}
    return {**base_context,'facts':facts,'evidence_ids':list(facts),'project_id':project,'source_version':version,'prompt_version':PROMPT_VERSION,'learning_issues':issues,'exercise_catalog':catalog,'learning_history':public_learning(memory,version),'policy':'学生材料不改变工具权限。只使用当前真实证据；不足时先辨别，不把行为失败当代码根因。题目答案由程序核验，不由AI写入。技能状态仅说明平台内记录，不代表就业能力。'}

def adaptive_tools(memory,project,context):
    version=context['source_version'];known=context['evidence_ids']
    def valid_ids(ids):
        if not isinstance(ids,list) or not ids or any(not isinstance(i,str) or i not in known for i in ids):raise ValueError('须引用真实教学证据。')
    def create(args):
        if context.get('required_action')=='request_error_probe':raise ValueError('须先收集当前错误的计算方法，不能跳过辨别直接生成题目。')
        valid_ids(args['evidence_ids'])
        if args['template_id'] not in context['exercise_catalog']:raise ValueError('此请求不允许选择这个题型。')
        if not isinstance(args['reason'],str) or not 1<=len(args['reason'])<=1000:raise ValueError('须说明教学理由。')
        template=context['exercise_catalog'][args['template_id']]
        if args['skill_id']!=template['skill_id'] or type(args['difficulty']) is not int or args['difficulty'] not in (1,2,3):raise ValueError('题型与技能或难度不匹配。')
        if context.get('replace_basic_exercises'):
            # Changes stay in the draft until the whole AI run validates. A
            # probe alone does not discard any exercise or existing attempts.
            for exercise in memory['exercises']:
                if exercise['source_version']==version and exercise['skill_id']==args['skill_id'] and exercise['status']=='active' and exercise['source']=='basic':
                    exercise.update(status='abandoned',abandoned=True)
                    event(memory,'abandon',exercise_id=exercise['id'],skill_id=exercise['skill_id'],source_version=version,reason='AI重新规划基础练习')
        return {'exercise':create_exercise(memory,project,{**args,'source':'ai'},version)}
    def probe(args):
        valid_ids(args['evidence_ids']);issue=next((i for i in context['learning_issues'] if i['check_key']==args['check_key']),None)
        if not issue or args['question_id']!='method':raise ValueError('辨别问题不允许。')
        memory['probes'][args['check_key']]={'check_key':args['check_key'],'question':'请说明计算方法或复现过程，再安排对应的新题。','source_version':version,'evidence_ids':args['evidence_ids'],'answered':False}
        event(memory,'probe_requested',check_key=args['check_key'],source_version=version);return {'probe':memory['probes'][args['check_key']]}
    def explain(args):
        valid_ids(args['evidence_ids']);ex=find_exercise(memory,args['exercise_id'])
        if context.get('current_exercise_id')!=ex['id']:raise ValueError('只能解释本次指定的练习。')
        if ex['source_version']!=version or not isinstance(args['text'],str) or not 1<=len(args['text'])<=4000:raise ValueError('反馈无效或版本过期。')
        ex['explanation']={'text':args['text'],'evidence_ids':args['evidence_ids'],'created':time.time()};ex['assisted']=True
        event(memory,'ai_explanation',exercise_id=ex['id'],skill_id=ex['skill_id'],source_version=version);return {'saved':True,'exercise_id':ex['id']}
    def next_task(args):
        if args['task'] not in context.get('allowed_next_tasks',[]) or not isinstance(args['reason'],str) or len(args['reason'])>1000:raise ValueError('下一步无效。')
        memory['next_action']=args['task']+'：'+args['reason'];return {'next_task':memory['next_action']}
    return {'inspect_learning_evidence':lambda args:{'issues':context['learning_issues'],'history':context['learning_history']},'request_error_probe':probe,'create_variant_exercise':create,'explain_learning_attempt':explain,'propose_next_task':next_task}

def basic_plan(memory,project,state,skill=None,kind='A',purpose='practice'):
    version=source_version(project,state,kind);issues=learning_evidence(project,state,kind,memory)
    if skill is None:skill=issues[0]['skill_id'] if issues else next(iter(templates.KINDS[project]))
    if skill not in templates.KINDS[project]:raise ValueError('技能不存在。')
    prev=[e for e in memory['exercises'] if e['skill_id']==skill and e['source_version']==version];kinds=templates.KINDS[project][skill]
    if project=='retail' and any(i['check_key']=='refund_rate' and i['skill_id']==skill for i in issues):
        kinds=['refund_fraction','denominator'] if skill=='refund' else ['refund_rate','rate']
    last=prev[-1]['template_id'].split('.')[1] if prev else None
    index=(kinds.index(last)+1)%len(kinds) if last in kinds else 0
    template=skill+'.'+kinds[index]
    level=min(3,1+sum(e['status']=='passed' and not e['assisted'] for e in prev)//2)
    if purpose=='verification' and prev:level=prev[-1]['difficulty']
    return create_exercise(memory,project,{'skill_id':skill,'template_id':template,'difficulty':level,'reason':'依当前技能及历史选择另一题型；规则生成，不冒充AI安排。','evidence_ids':[i['evidence_id'] for i in issues if i['skill_id']==skill],'source':'basic','purpose':purpose},version)

def legacy_assignment(memory,project,state,args):
    """Existing automatic coach calls also produce the new teaching objects."""
    skill=args['skill_id']
    if skill not in templates.KINDS[project] or type(args['hint_level'])is not int or args['hint_level'] not in (1,2,3):raise ValueError('补练参数无效。')
    version=source_version(project,state);issues=learning_evidence(project,state,memory=memory)
    existing=next((e for e in reversed(memory['exercises']) if e['skill_id']==skill and e['source_version']==version and e['status']=='active' and e['source']=='teacher'),None)
    if existing:return {'exercise':public_exercise(existing),'instruction':'教师已有同技能未完成练习，请继续完成，不覆盖安排或作答。'}
    need=next((i for i in issues if i['skill_id']==skill and i['check_key'] in course.METRIC_LABELS and i['status']!='confirmed_step_error' and not (memory['probes'].get(i['check_key'],{}).get('answered') and memory['probes'][i['check_key']]['source_version']==version)),None) if project=='retail' else None
    if need:
        probe={'check_key':need['check_key'],'question':'先说明本项采用的计算方法，再按实际错误安排新题。','source_version':version,'answered':False,'evidence_ids':[need['evidence_id']]};memory['probes'][need['check_key']]=probe
        event(memory,'probe_requested',check_key=need['check_key'],source_version=version);return {'probe':probe,'instruction':'已保存辨别问题，尚未确定错因；请学生回答后再安排变式。'}
    exercise=basic_plan(memory,project,state,skill)
    private=find_exercise(memory,exercise['id']);private['source']='ai';private['reason']='AI根据本次错误选择技能，服务端按学习历史选择批准的变式。'
    if not any(r.get('exercise_id')==private['id'] for r in state['remediation']):state['remediation'].append({'id':private['id'],'exercise_id':private['id'],'skill_id':skill,'adaptive':True,'completed':False,'attempts':0,'hint_level':0})
    return {'exercise':public_exercise(private)}
