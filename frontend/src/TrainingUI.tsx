import BrandMark from './BrandMark';
import {Check,ChevronRight,ArrowLeft,Layers3,LogOut,Sparkles,Settings2,CircleHelp} from 'lucide-react';
import type {Obj} from './api';
import {useEffect} from 'react';
import {TutorialButton} from './Tutorial';
import type {TutorialScope} from './tutorialContent';

export const purposeNames:Obj={diagnosis:'诊断与训练安排',feedback:'提交分析与补练',report:'报告审阅',defense:'作品答辩',portfolio:'作品整理',operator:'运营分析',adaptive_plan:'个性化练习安排',adaptive_feedback:'本题分步解释',engineering_diagnosis:'诊断与训练安排',requirements:'需求审阅',engineering_feedback:'调试与补练',engineering_report:'工程报告审阅',engineering_defense:'技术答辩',engineering_portfolio:'作品整理'};
export const actionNames:Obj={inspect_submission:'读取提交',check_metrics:'核对指标',lookup_skill_card:'查询知识卡',assign_remediation:'安排补练',propose_next_task:'安排下一步',ask_defense_question:'生成答辩追问',review_report:'保存报告评价',review_defense:'保存答辩评价',build_portfolio:'读取作品成果',operator_insights:'读取匿名运营汇总',request_human_review:'提交人工复核',inspect_learning_evidence:'读取学习证据',request_error_probe:'保存辨别追问',create_variant_exercise:'创建变式题',explain_learning_attempt:'保存个性化解释',read_source:'阅读源码',read_check_result:'读取核验结果',review_requirements:'审阅需求',review_engineering:'保存工程评价',review_engineering_defense:'保存答辩评价',build_engineering_portfolio:'整理工程作品'};

export function AgentResult({run}:{run:Obj}){
 const tokens=run.usage?.input_tokens!=null&&run.usage?.output_tokens!=null?run.usage.input_tokens+run.usage.output_tokens:null;
 return <article className="agent-result"><div className="agent-run-heading"><strong>{purposeNames[run.purpose]||'AI 教练答疑'}</strong><span>{run.status==='ok'?'反馈已生成':'本次需要重试'} · {run.model}</span></div><p className="agent-feedback" tabIndex={0}>{run.message}</p><div className="agent-actions">{run.actions?.map((a:Obj,i:number)=><span key={i} className={a.executed&&run.actions_committed!==false?'done':''}>{a.executed&&run.actions_committed!==false?<Check size={13}/>:<CircleHelp size={13}/>} {actionNames[a.tool]||'教练操作'}{!a.executed?' · 未执行':run.actions_committed===false?' · 未保存':''}</span>)}</div><small className="agent-run-meta">{new Date(run.created*1000).toLocaleString('zh-CN')} · {run.elapsed_ms?`${(run.elapsed_ms/1000).toFixed(1)} 秒`:'已记录'} · {tokens!==null?`${tokens} tokens`:'用量待确认'}{run.needs_human_review?' · 已请求人工复核':''}</small></article>;
}

export function AgentPanel({mode,auto,busy,active,canCoach,purpose,runs,latest,nextTask,description,onAuto,onCoach}:{mode:string;auto:boolean;busy:boolean;active:string;canCoach:boolean;purpose:string;runs:Obj[];latest?:Obj;nextTask?:string;description:string;onAuto:(v:boolean)=>void;onCoach:()=>void}){
 return <section className="panel agent-panel" aria-label="AI 教练工作记录"><div className="section-head"><div><h2><Sparkles size={20}/>你的 DeepSeek 实训教练</h2></div><span className="pill">{mode==='ai'?'已连接模型配置':'基础模式'}</span></div><p className="muted">{description}</p><div className="agent-controls"><label><input type="checkbox" checked={auto} disabled={busy||mode!=='ai'} onChange={e=>onAuto(e.target.checked)}/>提交后自动获得 AI 反馈</label><button className="button secondary" disabled={busy||!canCoach||mode!=='ai'} onClick={onCoach}><Sparkles size={16}/>{purposeNames[purpose]||'获取任务反馈'}</button></div>{active?<div role="status" className="agent-working"><span className="status-dot"/>DeepSeek 正在{purposeNames[active]||'处理当前任务'}，请稍候…</div>:latest?<AgentResult run={latest}/>:<div className="notice">{mode!=='ai'?'当前为基础模式，可继续完成练习与提交核验。':canCoach?'点击上方按钮，获取当前任务的个性化反馈。':'先完成当前阶段需要的提交，再获取 AI 反馈。'}</div>}{nextTask&&<p className="agent-next">下一步训练：<strong>{nextTask}</strong></p>}{runs.length>1&&<details><summary>查看 AI 协作历史（{runs.length} 次）</summary>{[...runs].reverse().map(r=><AgentResult key={r.id} run={r}/>)}</details>}</section>;
}

export function TrainingNavigation({user,title,stages,progress,page,busy,mode,onPage,onBack,onLogout,onSettings,tutorialScope}:{user:Obj;title:string;stages:string[];progress:Obj;page:number;busy:boolean;mode:string;onPage:(page:number)=>void;onBack:()=>void;onLogout:()=>void;onSettings?:()=>void;tutorialScope?:TutorialScope}){
 useEffect(()=>{window.scrollTo({top:0,behavior:'auto'})},[page]);
 return <><div className="brand"><BrandMark/><div>我要实习</div></div><button className="nav-item project-back" disabled={busy} onClick={onBack}><ArrowLeft size={17}/>返回项目库</button><div className="sidebar-course" title={title}>{title}</div><button className={'nav-item '+(page===-1?'selected':'')} aria-current={page===-1?'page':undefined} onClick={()=>onPage(-1)}><Layers3 size={18}/>项目概览</button><div data-tour="course-navigation" className="nav-section">按顺序完成训练</div>{stages.map((name,i)=><button key={name} className={'nav-item '+(page===i?'selected':'')} aria-current={page===i?'page':undefined} disabled={i>progress.stage} onClick={()=>onPage(i)}><span className="stage-number">{String(i+1).padStart(2,'0')}</span>{name}{progress.completed?.[i]&&<Check className="nav-check" size={14}/>}</button>)}<div className="sidebar-bottom">{tutorialScope&&<TutorialButton scope={tutorialScope}/>}<div className="mode-card"><span className={'status-dot '+(mode==='ai'?'':'basic')}/><strong>{mode==='ai'?'AI 教练已启用':'基础训练模式'}</strong><p>{mode==='ai'?'遇到问题，点右下角「问AI教练」':'核验与标准练习正常可用'}</p></div>{onSettings&&<button className="nav-item" onClick={onSettings}><Settings2 size={17}/>使用与数据说明</button>}<button className="nav-item" onClick={onLogout}><LogOut size={17}/>退出工作室</button><div className="profile"><span>{user.username.slice(0,1).toUpperCase()}</span><div>{user.username}<small>学生{user.is_demo?' · 演示账号':''}</small></div></div></div></>;
}

export function TrainingTopbar({title,page,stages}:{title:string;page:number;stages:string[]}){
 return <header className="topbar"><div><span className="course-breadcrumb" title={title}>{title}</span><ChevronRight size={14}/><strong>{page===-1?'项目概览':stages[page]}</strong></div></header>;
}

export function TrainingProgress({progress,stages,onContinue}:{progress:Obj;stages:string[];onContinue:()=>void}){
 return <section data-tour="current-task" className="training-progress" aria-label="实训进度"><div><span>本项目进度</span><strong>{progress.percent}%</strong></div><progress max={100} value={progress.percent} aria-label="已完成训练进度"/><button className="text-link" onClick={onContinue}>{progress.finished?'查看我的作品':'当前任务：'+stages[progress.stage]}<ChevronRight size={15}/></button></section>;
}

export function TrainingOverviewHeading(){
 return <div className="page-header"><h1>让能力，留下证据。</h1></div>;
}

export function TrainingRoadmap({stages,progress,onPage}:{stages:string[];progress:Obj;onPage:(page:number)=>void}){
 return <><div className="section-head route-heading"><div><h2>你的能力路径</h2></div><span className="pill">{progress.completed.filter(Boolean).length} / {stages.length} 已完成</span></div><div className="path-grid">{stages.map((name,i)=><button key={name} disabled={i>progress.stage} onClick={()=>onPage(i)} className={'path-step '+(progress.completed[i]?'done':i===progress.stage?'active':'')}><span className="step-number">{progress.completed[i]?<Check size={17}/>:String(i+1).padStart(2,'0')}</span><strong>{name}</strong><small>{progress.completed[i]?'已完成':i===progress.stage?'从这里继续':'等待前序任务'}</small><ChevronRight size={16}/></button>)}</div></>;
}
