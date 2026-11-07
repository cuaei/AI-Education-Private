"""Public engineering curriculum, independent progress, and versioned evidence."""
import html
import json
import secrets
import time

PROJECT='software-engineering'
VERSION='se-2026.10.12.1'
TITLE='校园活动报名系统的迭代交付'
STAGES=['起点诊断','需求与验收','读代码与复现','后端修复','前端与回归','工程评审与答辩','独立需求变更','工程作品交付']
RULES=[
 '学生查看活动、报名、查看和取消本人报名；组织者发布活动及查看自己活动名单。',
 '容量为正整数，截止不晚于开始时间；发布后容量固定。',
 '重复报名/取消返回当前状态，不重复占用/释放名额；取消后截止前可重新报名。',
 '截止瞬间即停止报名和取消，已取消记录保留。',
 '身份由服务端会话取得，学生不能取消他人记录或读取组织者名单。',
 '有效报名人数不能超过容量，同时抢最后一个名额只能一人成功。',
 '页面呈现加载、空列表、成功、满额、截止、无权限及本人报名状态。',
 '登录401、无权限403、不存在404、满额/截止409、输入无效422；重复操作幂等200。'
]
B_RULES=['满额时可选择候补，候补不占有效名额。','不能同时有效报名和候补，重复请求不重复排队。','有效报名取消时按稳定入队先后递补一人；取消候补不释放有效名额。','并发、截止和权限遵循A规则；页面区分confirmed、waiting、cancelled。']
QUIZ=[
 {'skill':'http','question':'服务端收到未登录的报名请求，应如何处理？','options':['401，要求登录','直接信任请求中的student_id','先报名再验证'],'answer':0,'weight':3},
 {'skill':'auth','question':'取消报名时，身份应从哪里获得？','options':['页面输入框','服务端认证会话','请求中的任意用户名'],'answer':1,'weight':3},
 {'skill':'state','question':'同一报名重复取消，应该怎样计算名额？','options':['每次释放一个','第二次再扣回去','只释放一次'],'answer':2,'weight':3},
 {'skill':'transaction','question':'两个请求争抢最后一个名额，正确的处理是？','options':['前端禁用按钮就足够','容量检查和写入在一个原子事务中','只延迟其中一个请求'],'answer':1,'weight':4},
 {'skill':'testing','question':'修复重复报名后，哪种测试最有帮助？','options':['重复提交并检查人数不增加','只看页面颜色','统计代码行数'],'answer':0,'weight':4},
 {'skill':'frontend','question':'接口返回满额冲突时页面应怎样做？','options':['仍显示报名成功','忽略响应','展示原因并刷新真实名额'],'answer':2,'weight':3}
]
POSTQUIZ=[
 {'skill':'http','question':'活动ID不存在且已登录，应返回？','options':['200并伪造一个活动','404','401'],'answer':1,'weight':3},
 {'skill':'auth','question':'学生修改请求里的报名ID为别人的记录，应？','options':['拒绝取消且不修改人数','允许操作','只隐藏按钮'],'answer':0,'weight':3},
 {'skill':'state','question':'取消后重新报名，记录应如何处理？','options':['删除所有历史','截止前允许再次有效报名并保留历史','永远禁止'],'answer':1,'weight':3},
 {'skill':'transaction','question':'容量查询和插入间隔会带来哪种风险？','options':['字体变化','密码自动失效','并发超过容量'],'answer':2,'weight':4},
 {'skill':'testing','question':'自己的测试只对正确版本通过，还应检查？','options':['能否发现预设故障版本','是否只有一行','文件名长度'],'answer':0,'weight':4},
 {'skill':'frontend','question':'请求处理中用户重复点击时，应该？','options':['提交多次直到成功','不显示状态','显示加载并避免重复操作，后端仍须幂等'],'answer':2,'weight':3}
]
CARDS={
 'http':{'title':'HTTP与错误处理','body':'状态码表达实际结果。未登录401、资源不存在404、业务冲突409。','question':'未登录请求应返回哪个状态码？','answer':'401'},
 'auth':{'title':'角色和资源归属','body':'认证确定是谁，授权确定能做什么。每个写接口都核验角色和归属。','question':'学生能取消其他人的报名吗？填写“不能”。','answer':'不能'},
 'state':{'title':'幂等与状态机','body':'重复请求不应重复改变名额；cancelled只释放一次。','question':'同一有效报名取消两次，一共释放几个名额？','answer':'1'},
 'transaction':{'title':'并发和事务','body':'多个请求会交错执行。检查容量与写入须放在同一事务，失败应回滚。','question':'“先查询，事务外再插入”能保证不超容量吗？填写“不能”。','answer':'不能'},
 'testing':{'title':'回归与故障检测','body':'验证结果与状态，覆盖重复请求、未授权、容量边界。不要只断言接口没有崩溃。','question':'只运行空测试能证明修复有效吗？填写“不能”。','answer':'不能'},
 'frontend':{'title':'前后端联调','body':'页面按真实响应显示加载、错误和成功；权限仍由服务端保证。','question':'发生业务冲突的HTTP状态码？','answer':'409'}
}
ENGINEERING_CRITERIA=['需求追溯','设计可维护性','缺陷分析','测试解释','交付与协作说明']
DEFENSE_CRITERIA=['业务理解','实现方法','测试与限制']
QUESTIONS=['解释重复报名与重复取消如何保持幂等，并指出你的实现位置。','两个人同时抢最后一个名额时，为什么前端禁用按钮不够？你的后端怎样保证一致性？','你怎样验证权限、截止边界和回归？你的测试和系统还存在哪些限制？']

def initial_state():
    return {'project_id':PROJECT,'course_version':VERSION,'enrollment_id':secrets.token_hex(10),'revision':0,'diagnostic':None,'posttest':None,'requirements':'','reproduction':'','submissions':[], 'jobs':[], 'grade':None,'report':'','report_review':None,'defense':[],'defense_review':None,'defense_hash':None,'transfer':None,'b_mode':'independent','b_mode_history':[], 'agent_runs':[],'remediation':[],'human_reviews':[],'feedback':[],'chats':[],'work_history':[],'portfolio_note':'','next_task':STAGES[0]}

def quiz_public(post=False):
    return [{k:v for k,v in q.items() if k!='answer'} for q in (POSTQUIZ if post else QUIZ)]

def quiz_grade(answers,post=False):
    questions=POSTQUIZ if post else QUIZ
    if not isinstance(answers,list) or len(answers)!=6 or any(type(a)is not int or not 0<=a<3 for a in answers):raise ValueError('请完成全部六题。')
    checks=[{'key':q['skill'],'label':q['question'],'passed':a==q['answer'],'weight':q['weight']} for q,a in zip(questions,answers)]
    return {'score':sum(c['weight'] for c in checks if c['passed']),'max_score':20,'checks':checks,'answers':answers,'weak_skills':[c['key'] for c in checks if not c['passed']],'created':time.time()}

def latest_submission(state,kind='A'):
    return next((s for s in reversed(state['submissions']) if s['kind']==kind),None)

def progress(state):
    g=state.get('grade') or {};checks=g.get('checks',[])
    backend_ok=bool(checks) and all(c['passed'] for c in checks if c['dimension']=='business')
    completed=[bool(state['diagnostic']),bool(state['requirements']),bool(state['reproduction']),backend_ok,bool(g.get('passed')),bool(state['report']) and len(state['defense'])>=3 and all(t.get('answer') for t in state['defense'][:3]) and bool(state['posttest']),bool(state['transfer']),bool(state['portfolio_note']) and bool(state['transfer'])]
    stage=next((i for i,c in enumerate(completed) if not c),7)
    return {'completed':completed,'stage':stage,'percent':round(sum(completed)/8*100),'finished':all(completed)}

def public_meta():
    return {'id':PROJECT,'title':TITLE,'version':VERSION,'stages':STAGES,'rules':RULES,'b_rules':B_RULES,'quiz':quiz_public(),'postquiz':quiz_public(True),'cards':{k:{a:b for a,b in c.items() if a!='answer'} for k,c in CARDS.items()},'technology':'Python / FastAPI / SQLite / React / TypeScript','estimated_hours':'16—24小时（设计估计）','accounts':'student1 / student2 / student3 / student4 / organizer / organizer2；密码统一 Demo2026!（仅虚构训练应用）'}

def evidence(state):
    facts={'task:rules':{'text':'\n'.join(RULES)}}
    if state['diagnostic']:facts['diagnostic:1']=state['diagnostic']
    for k in ('requirements','reproduction','report'):
        if state[k]:facts[k+':current']={'text':state[k]}
    s=latest_submission(state)
    if s:facts['submission:'+s['hash']]={'hash':s['hash'],'version':s['version'],'files':s['files'],'description':s['description']}
    if state['grade']:
        for c in state['grade']['checks']:facts['check:'+state['grade']['job_id']+':'+c['key']]=c
    for i,t in enumerate(state['defense']):
        if t.get('answer'):facts[f'defense:{i+1}']={'text':t['answer'],'question':t['question'],'hash':state['defense_hash']}
    return facts

def response(state):
    return {**state,'progress':progress(state),'objective_score':(state.get('grade') or {}).get('score',0),'evidence':evidence(state)}

def portfolio(state,private=False,include_defense=False,include_reviews=False):
    out={'project_id':PROJECT,'title':TITLE,'disclaimer':'原创模拟岗位实训；不代表企业实习或真实客户项目。','version':VERSION,'progress':progress(state),'requirements':state['requirements'],'reproduction':state['reproduction'],'report':state['report'],'grade':state['grade'],'transfer':state['transfer'],'diagnostic':state['diagnostic'],'posttest':state['posttest'],'note':state['portfolio_note'],'ai_runs':len(state['agent_runs']),'submissions':[{k:v for k,v in s.items() if k not in ('archive_path',)} for s in state['submissions']]}
    if private or include_defense:out['defense']=state['defense']
    if private or include_reviews:out.update(report_review=state['report_review'],defense_review=state['defense_review'])
    if private:out.update(ai_history=state['agent_runs'],chats=state.get('chats',[]),history=state['work_history'])
    return out

def export_markdown(state):
    data=portfolio(state,True)
    lines=[f'# {TITLE}',data['disclaimer'],f"客观核验：{response(state)['objective_score']}/60",'## 需求与验收',state['requirements'],'## 故障复现',state['reproduction'],'## 工程报告',state['report'],'## 发布说明',state['portfolio_note'],'## 私人答辩']
    for t in state['defense']:lines.extend([t['question'],t.get('answer','')])
    lines.extend(['## 实际核验与AI协作记录','```json',json.dumps(data,ensure_ascii=False,indent=2),'```'])
    return '\n\n'.join(lines)

def export_html(state):
    return '<!doctype html><meta charset="utf-8"><title>工程作品集</title><style>body{max-width:900px;margin:40px auto;font:16px/1.8 sans-serif}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><pre>'+html.escape(export_markdown(state))+'</pre>'
