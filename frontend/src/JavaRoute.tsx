import StudentClasses from './StudentClasses';
import JavaCourse from './JavaCourse';
import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import './java-route.css';
type Topic={id:string;title:string;resource:{id:string;title:string;url:string}|null};
type Data={topics:Topic[];completed:string[];remaining:number;ai_enabled:boolean};
export default function JavaRoute({user,onLogout}:{user:Record<string,any>;onLogout:()=>void}){
 const [classesOpen,setClassesOpen]=useState(false);
 const [course,setCourse]=useState(false);
 const [data,setData]=useState<Data|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[question,setQuestion]=useState(''),[answer,setAnswer]=useState('');
 async function load(){try{setData(await api('/java-route'))}catch(e){setError(e instanceof Error?e.message:'载入失败')}}
 useEffect(()=>{void load()},[]);
 const toggling=useRef(false);
 async function toggle(id:string,completed:boolean){
  if(toggling.current)return;
  toggling.current=true;setBusy(true);setError('');
  const before=data?.completed??[];
  setData(current=>current?{...current,completed:completed?[...current.completed.filter(x=>x!==id),id]:current.completed.filter(x=>x!==id)}:current);
  try{await api('/java-route/progress',{resource_id:id,completed});await load()}
  catch(e){setData(current=>current?{...current,completed:before}:current);setError(e instanceof Error?e.message:'保存失败')}
  finally{toggling.current=false;setBusy(false)}
 }
 async function ask(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{const r=await api('/java-route/ask',{question});setAnswer(r.message);setQuestion('');await load()}catch(e){setError(e instanceof Error?e.message:'提问失败')}finally{setBusy(false)}}
 if(course)return <JavaCourse onBack={()=>setCourse(false)}/>;
 return <div className="java-shell"><header className="java-top"><div className="brand"><span className="brand-mark"/>我要实习</div><div><button className="button secondary" onClick={()=>setClassesOpen(true)}>我的班级</button><span>{user.username}</span><button className="button secondary" onClick={onLogout}>退出登录</button></div></header><main className="java-main"><section className="java-intro"><p>从学习到应用</p><h1>Java 后端工程师学习路线</h1><p>从基础开始，按自己的节奏学习。已掌握的内容可以跳过，学习资料由外部网站提供。</p><strong>{data?.completed.length??0} 项资料已标记完成</strong><p>标记只记录进度，不代表能力测评通过。</p></section>{error&&<div className="alert" role="alert">{error}</div>}<div className="java-layout"><section aria-label="学习路线"><h2>你的学习路线</h2><p>按顺序了解，也可以自由选择主题。</p>{!data&&<p>正在加载学习路线…</p>}{data?.topics.map((topic,index)=><article className="java-topic" key={topic.id}><span className="java-index">{String(index+1).padStart(2,'0')}</span><div><h3>{topic.title}</h3>{topic.resource?<><a className="java-link" href={topic.resource.url} target="_blank" rel="noopener noreferrer">{topic.resource.title}</a><p>外部候选资料 · 免费情况与访问状态待核实</p><label><input type="checkbox" disabled={busy} checked={data.completed.includes(topic.resource.id)} onChange={e=>void toggle(topic.resource!.id,e.target.checked)}/> 标记这项资料已学习</label></>:<p>中文免费资料待核实，暂未提供推荐链接。</p>}</div></article>)}<section className="java-next"><h2>下一步：综合实作与模拟实习</h2><p>综合实作使用「比赛报名系统」场景，与之后的网上商店不同。通过后依序完成查询商品、建立订单、查看订单三项实习工作。</p><button className="button" onClick={()=>setCourse(true)}>进入综合实作与模拟实习</button><p>这是网站内的模拟流程，不安排真实公司的实习。练习示例已并入综合实作，可在工作台下载起始项目。</p></section></section><aside className="java-help"><h2>学习中遇到问题？</h2><p>不懂的概念可以问 AI。每人每天 10 次，主动发送才会使用次数。</p><strong>今日剩余 {data?.remaining??'—'} 次</strong>{data&&!data.ai_enabled&&<p>AI 暂未配置，请联系管理员。</p>}<form onSubmit={ask}><label htmlFor="java-question">你的问题</label><textarea id="java-question" value={question} onChange={e=>setQuestion(e.target.value)} maxLength={2000} placeholder="例如：类和对象有什么区别？"/><button className="button" disabled={busy||!question.trim()||!data?.remaining||!data?.ai_enabled}>发送问题</button></form>{answer&&<div className="java-answer"><h3>AI 回答</h3><p>{answer}</p></div>}<p>请求失败也可能产生费用，并计入当天次数。</p></aside></div></main>{classesOpen&&<StudentClasses onClose={()=>setClassesOpen(false)} onSelect={()=>{}} hideTrainingLinks/>}</div>
}
