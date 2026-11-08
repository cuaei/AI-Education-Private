import BrandMark from './BrandMark';
import {useCallback,useEffect,useState} from 'react';
import {ArrowRight,Code2,FileChartColumn,LogOut,Compass,LockKeyhole,ChevronDown} from 'lucide-react';
import {api,type Obj} from './api';
import StudentTutorial,{TutorialButton} from './Tutorial';
import StudentClasses from './StudentClasses';

export default function ProjectLibrary({user,onSelect,onLogout}:{user:Obj;onSelect:(id:string)=>void;onLogout:()=>void}){
 const [classesOpen,setClassesOpen]=useState(false);
 const closeClasses=useCallback(()=>setClassesOpen(false),[]);
 const [projects,setProjects]=useState<Obj[]>([]),[professional,setProfessional]=useState('全部'),[error,setError]=useState(''),[loading,setLoading]=useState(true),[revision,setRevision]=useState(0);
 useEffect(()=>{window.scrollTo({top:0,behavior:'auto'})},[]);
 useEffect(()=>{let alive=true;setLoading(true);setError('');api('/projects').then(r=>{if(alive)setProjects(r.projects)}).catch(e=>{if(alive)setError(e.message)}).finally(()=>{if(alive)setLoading(false)});return()=>{alive=false}},[revision]);
 const professions=[...new Set(projects.flatMap(p=>p.professional))] as string[];
 const visible=projects.filter(p=>professional==='全部'||p.professional.includes(professional));
 const available=visible.filter(p=>p.availability==='available'),upcoming=visible.filter(p=>p.availability==='upcoming');
 const totalAvailable=projects.filter(p=>p.availability==='available').length;
 const continuing=projects.filter(p=>p.availability==='available'&&p.progress?.percent>0&&!p.progress?.finished);
 return <div className="project-library library-v2"><header><div className="brand"><BrandMark/><div>我要实习</div></div><div className="library-account"><button className="button secondary" onClick={()=>setClassesOpen(true)}>我的班级</button><TutorialButton scope="library"/><span>{user.username} 的实训空间</span><button className="button secondary" onClick={onLogout}><LogOut size={16}/>退出</button></div></header><main>
  <section className="library-intro"><div className="library-thesis"><h1>从你的专业出发，<br/>完成一份能展示的作品。</h1><p>选择一项实训，跟着任务完成提交、修改和交付。遇到不会的问题，可以随时向 AI 教练提问。</p><a className="button" href="#choose-project">选择我的实训<ChevronDown size={17}/></a><span className="library-cross-major">可以跨专业选择，每个项目分别保存学习进度。</span></div><div className="learning-route"><h2><Compass size={20}/>第一次来？这样开始</h2><ol><li><span>01</span><div><strong>选择专业方向</strong><p>筛选与你的专业有关的项目，也可以查看全部。</p></div></li><li><span>02</span><div><strong>看看要做什么、交付什么</strong><p>根据项目任务和最终成果，选择想练习的岗位能力。</p></div></li><li><span>03</span><div><strong>从起点诊断开始</strong><p>进入后按阶段完成任务；提交反馈会指出需要修改的地方。</p></div></li></ol></div></section>
  {continuing.length>0&&<section className="continue-strip" aria-label="继续我的实训"><div><strong>接着上次的进度</strong><span>你有 {continuing.length} 个已开始的项目</span></div><div className="continue-actions">{continuing.map(p=><button className="button secondary" key={p.id} onClick={()=>onSelect(p.id)}>{p.id==='retail'?'销售分析':'软件工程'} · {p.progress.percent}%<ArrowRight size={15}/></button>)}</div></section>}
  <section data-tour="project-catalog" className="library-selection" id="choose-project"><div className="library-section-heading"><div><h2>找到适合你的实训</h2></div><span>{loading?'正在加载项目…':`${totalAvailable} 个项目可开始 · 其余方向筹备中`}</span></div><div data-tour="profession-filter" className="professional-tabs" role="group" aria-label="按专业筛选">{['全部',...professions].map(p=><button type="button" aria-pressed={p===professional} className={p===professional?'selected':''} key={p} onClick={()=>setProfessional(p)}>{p}</button>)}</div><p className="filter-explanation">{professional==='全部'?'查看全部方向。先选择一个已开放的项目开始练习。':`正在查看「${professional}」方向。专业只用于筛选，不限制你学习其他项目。`}</p>
  {error&&<div role="alert" className="alert">项目加载失败：{error}<button className="button secondary" onClick={()=>setRevision(r=>r+1)}>重新加载</button></div>}
  {loading?<div className="library-empty" role="status">正在读取项目与学习进度…</div>:!error&&<>
   <div className="catalog-label"><h3>现在可以开始</h3><span>{available.length} 个项目</span></div>
   {available.length>0?<div className="course-cards">{available.map(p=><section data-tour="available-project" className="panel course-card" key={p.id}><div className="course-card-heading"><span className="course-symbol">{p.id==='retail'?<FileChartColumn size={27}/>:<Code2 size={27}/>}</span><span className="availability-badge">已开放</span></div><span className="eyebrow">{p.role}</span><h2>{p.title}</h2><p className="course-description">{p.description}</p><div className="project-tags">{p.professional.map((t:string)=><span key={t}>{t}</span>)}</div><dl><div><dt>最终交付</dt><dd>{p.deliverable}</dd></div><div><dt>练习材料与工具</dt><dd>{p.technology}</dd></div><div><dt>学习投入</dt><dd>{p.hours}</dd></div></dl><div className="course-progress"><div><span>{p.progress?.percent?'已保存的训练进度':'从起点诊断开始'}</span><strong>{p.progress?.percent||0}%</strong></div><progress max={100} value={p.progress?.percent||0} aria-label={p.title+'的完成进度'}/></div><button data-tour="enter-project" className="button" onClick={()=>onSelect(p.id)}>{p.progress?.finished?'进入已完成实训':p.progress?.percent?'继续实训':'开始实训'}<ArrowRight size={16}/></button></section>)}</div>:<div className="library-empty"><Compass size={25}/><h3>这个专业的实训正在筹备</h3><p>目前还没有可开始的项目。你可以先体验其他专业已开放的实训。</p><button className="button secondary" onClick={()=>setProfessional('全部')}>查看已开放项目<ArrowRight size={16}/></button></div>}
   {upcoming.length>0&&<section className="upcoming-section"><div className="catalog-label"><h3>更多专业 · 筹备中</h3></div><div className="upcoming-grid">{upcoming.map(p=><article className="upcoming-card" key={p.id}><div className="upcoming-card-heading"><span>{p.professional.join(' / ')}</span><LockKeyhole size={16}/></div><h3>{p.title}</h3><p>项目内容筹备中，暂时无法开始实训。</p><button className="button secondary" disabled>筹备中 · 暂未开放</button></article>)}</div></section>}
  </>}
  </section>
 </main><StudentTutorial userId={user.id} scope="library"/>{classesOpen&&<StudentClasses onClose={closeClasses} onSelect={onSelect}/>}</div>;
}
