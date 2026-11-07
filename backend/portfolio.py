"""Student-confirmed artifacts. HTML escapes all student/model content."""
import html
from .course import VERSION


def objective_score(state):
    return sum((v or {}).get('score',0) for v in state['grades'].values())


def progress(state):
    g=state['grades']
    completed=[bool(state['diagnostic']),bool(g['clean'] and g['clean']['passed']),bool(g['metrics'] and g['metrics']['passed']),bool(g['groups'] and g['groups']['passed']),bool(state['report'] and not state['report_stale']),sum(bool(t.get('answer')) for t in state['defense'])>=3,bool(state['transfer']),False]
    completed[-1]=all(completed[:-1])
    return {'completed':completed,'stage':next((i for i,ok in enumerate(completed) if not ok),7),'percent':round(sum(completed)/8*100),'finished':all(completed)}


def public_portfolio(state,include_defense=False,include_reviews=False):
    p={'title':'校园文创店销售分析与运营建议','disclaimer':'模拟岗位实训；合成训练数据，不代表企业实习或真实经营。','course_version':VERSION,'progress':progress(state),'objective_score':objective_score(state),'metrics':state['metrics'] if (state['grades']['metrics'] or {}).get('passed') else {},'tables':state['tables'] if (state['grades']['groups'] or {}).get('passed') else {},'report':state['report'] if not state['report_stale'] else None,'report_stale':state['report_stale'],'note':state['portfolio_note'],'ai_assistance':{'real_ai_runs':len(state['agent_runs']),'hint_count':len(state['remediation']),'submission_versions':len(state['submissions'])},'transfer':({'score':state['transfer']['evaluation']['score'],'max_score':25,'posttest_score':state['transfer']['posttest']['score']} if state['transfer'] else None)}
    if include_defense and not state['report_stale']:p['defense_excerpt']=[{'question':t['question'],'answer':t['answer']} for t in state['defense'] if t.get('answer')][:1]
    if include_reviews and not state['report_stale']:p['evaluations']={k:state[k] for k in ('report_review','defense_review')}
    return p


def export_markdown(state):
    p=public_portfolio(state);report=p['report'] or {}
    lines=['# '+p['title'],'',p['disclaimer'],'','课程版本：'+VERSION,'状态：'+('已完成' if p['progress']['finished'] else '进行中'),'客观核验：'+str(p['objective_score'])+'/60','']
    if p['report_stale']:lines+=['**报告引用的数据已变化，需要重新核验。**','']
    lines+=['## 已核验指标','']+[f'- {k}: {v}' for k,v in p['metrics'].items()]
    for dimension,rows in p['tables'].items():
        lines+=['','## 分组表：'+dimension,'','| 名称 | 前期 | 当期 |','| --- | ---: | ---: |']+[f"| {r['name']} | {r['baseline'] if r['baseline'] is not None else '—'} | {r['current']} |" for r in rows]
    lines+=['','## 观察与依据','']+[f"- {r['text']}（证据：{r['evidence_id']}）" for r in report.get('observations',[])]
    lines+=['','## 运营建议','']+[f"- {r['text']}\n  依据：{r['evidence_id']}\n  验证：{r['validation']}" for r in report.get('recommendations',[])]
    lines+=['','## 限制说明','',report.get('limitations','尚未提交。'),'','## 学生确认的补充说明','',p['note'] or '无','', '## 协作记录','',f"提交 {len(state['submissions'])} 个版本；真实 AI 调用 {len(state['agent_runs'])} 次；补练 {len(state['remediation'])} 次。"]
    if p['transfer']:lines+=['',f"独立迁移指标：{p['transfer']['score']}/25；结业测评：{p['transfer']['posttest_score']}/6。"]
    if not state['report_stale']:
        for label,key in (('报告评价','report_review'),('答辩评价','defense_review')):
            review=state[key]
            if review:
                lines+=['','## '+label,'',f"{review['score']}/{review['max_score']} · 来源：{review['source']}（训练评价）"]
                lines += [f"- {r['criterion']} {r['score']}/5：{r['reason']}；原文：{r['quote']}；证据：{r['evidence_id']}" for r in review.get('criteria',[])]
        lines+=['','## 私人答辩记录（下载版）','']+[f"- 问：{t['question']}\n  答：{t['answer']}" for t in state['defense'] if t.get('answer')]
    lines+=['','## 修改过程','']+[f"- 提交版本 {s['version']}：{s['kind']}，核验 {s['evaluation']['score']}/{s['evaluation']['max_score']}" for s in state['submissions']]
    lines += [f"- 已保留历史作品 {i+1}，报告编号 {(h.get('report') or {}).get('id','无')}；历史内容与当前作品分开保存。" for i,h in enumerate(state.get('work_history',[]))]
    return '\n'.join(lines)


def export_html(state):
    p=public_portfolio(state)
    text=html.escape(export_markdown(state))
    bars=''
    if p['tables']:
        data=p['tables'].get('category',[]);maximum=max((max(float(r['baseline']),float(r['current'])) for r in data),default=1) or 1
        for r in data:
            bars+=f"<div class='row'><b>{html.escape(r['name'])}</b><i style='width:{float(r['baseline'])/maximum*70:.2f}%'>{float(r['baseline']):.2f}</i><i class='current' style='width:{float(r['current'])/maximum*70:.2f}%'>{float(r['current']):.2f}</i></div>"
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>实战作品集</title><style>body{max-width:900px;margin:48px auto;font:16px/1.8 system-ui;padding:24px;color:#153e44}pre{white-space:pre-wrap;font:inherit}.row{margin:20px 0}.row b{display:block}.row i{display:block;background:#cbdfe3;margin:4px 0;padding:4px;min-width:70px;font-style:normal}.row .current{background:#68b9ad}@media print{body{margin:0}}</style><body><pre>'+text+'</pre>'+bars+'</body></html>'
