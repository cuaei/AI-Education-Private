import {useEffect,useId,useMemo,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {ArrowLeft,ArrowRight,BookOpen,Check,LoaderCircle,X} from 'lucide-react';
import {api,pendingOperations,reportError} from './api';
import {tutorialSteps,TUTORIAL_VERSION,type TutorialContext,type TutorialScope} from './tutorialContent';
import './tutorial.css';

type RecordState={version:string;status:'new'|'in_progress'|'completed'|'skipped';step:number;step_count:number};
type Rect={left:number;top:number;right:number;bottom:number;width:number;height:number};
export function TutorialButton({scope}:{scope:TutorialScope}){
 return <button type="button" className="nav-item tutorial-entry" onClick={()=>window.dispatchEvent(new CustomEvent('tutorial-open',{detail:{scope}}))}><BookOpen size={17}/>使用教程</button>;
}

export default function StudentTutorial({userId,scope,context,onPrepare,onFinish}:{userId:string;scope:TutorialScope;context?:TutorialContext;onPrepare?:()=>void;onFinish?:()=>void}){
 const steps=useMemo(()=>tutorialSteps(scope,context),[scope,context?.stage,context?.hasDiagnostic,context?.independent,context?.stageTitle,context?.finished]);
 const [record,setRecord]=useState<RecordState|null>(null),[mode,setMode]=useState<'closed'|'welcome'|'active'>('closed'),[index,setIndex]=useState(0),[saving,setSaving]=useState(false),[error,setError]=useState(''),[loading,setLoading]=useState(true),[paused,setPaused]=useState(false),[blocked,setBlocked]=useState(false),[rect,setRect]=useState<Rect|null>(null),[viewport,setViewport]=useState({width:window.innerWidth,height:window.innerHeight});
 const portal=useRef<HTMLDivElement>(null),card=useRef<HTMLElement>(null),alive=useRef(true),savingRef=useRef(false),manual=useRef(false),request=useRef<AbortController|null>(null),lastFocus=useRef<HTMLElement|null>(null),blockedRef=useRef(false);
 const afterClose=useRef<(()=>void)|null>(null);
 const [minimumHeight,setMinimumHeight]=useState(360),[fallbackTarget,setFallbackTarget]=useState(false);
 const maskId='tour-mask-'+useId().replace(/:/g,'');const step=steps[Math.min(index,steps.length-1)];
 const visible=mode!=='closed'&&!paused;

 async function load(signal?:AbortSignal){
  setLoading(true);setError('');
  try{const r=await api('/tutorial/'+scope,undefined,undefined,signal);if(!alive.current||signal?.aborted)return;if(r.version!==TUTORIAL_VERSION||r.step_count!==steps.length)throw new Error('教程内容与服务版本不一致，请刷新页面后再打开教程。');setRecord(r);if(manual.current||r.status==='new'||r.status==='in_progress'){lastFocus.current=document.activeElement as HTMLElement;setMode('welcome')}}
  catch(e){if(alive.current&&!signal?.aborted)setError(reportError(e,'教程暂未读取'))}
  finally{if(alive.current&&!signal?.aborted)setLoading(false)}
 }
 useEffect(()=>{alive.current=true;const controller=new AbortController();load(controller.signal);return()=>{alive.current=false;controller.abort();request.current?.abort()}},[userId,scope]);
 useEffect(()=>{
  const open=(event:Event)=>{if((event as CustomEvent).detail.scope!==scope)return;manual.current=true;lastFocus.current=document.activeElement as HTMLElement;setMode('welcome');if(!record&&!loading)load()};
  window.addEventListener('tutorial-open',open);return()=>window.removeEventListener('tutorial-open',open);
 },[scope,record,loading]);

 async function persist(status:string,next:number){
  const controller=new AbortController();request.current=controller;
  const r=await api('/tutorial/'+scope,{version:TUTORIAL_VERSION,status,step:next},undefined,controller.signal);
  if(alive.current)setRecord(r);return r;
 }
 async function begin(fromStart=false){
  if(!record||savingRef.current)return;savingRef.current=true;setSaving(true);setError('');
  const next=fromStart?0:Math.min(record.status==='in_progress'?record.step:0,steps.length-1);
  try{await persist('in_progress',next);if(!alive.current)return;onPrepare?.();setIndex(next);setMode('active');setPaused(blockedRef.current)}
  catch(e){if(alive.current&&!request.current?.signal.aborted)setError(reportError(e,'教程进度暂未保存'))}
  finally{savingRef.current=false;if(alive.current)setSaving(false)}
 }
 async function move(next:number){
  if(savingRef.current||next<0||next>=steps.length)return;savingRef.current=true;setSaving(true);setError('');
  try{await persist('in_progress',next);if(alive.current)setIndex(next)}
  catch(e){if(alive.current&&!request.current?.signal.aborted)setError(reportError(e,'教程进度暂未保存'))}
  finally{savingRef.current=false;if(alive.current)setSaving(false)}
 }
 async function end(status:'completed'|'skipped'){
  if(savingRef.current)return;savingRef.current=true;setSaving(true);setError('');
  try{if(record)await persist(status,status==='completed'?steps.length-1:index);if(!alive.current)return;afterClose.current=()=>{if(status==='completed')onFinish?.();const target=status==='completed'?document.querySelector<HTMLElement>(scope==='library'?'[data-tour="enter-project"]':'[data-tour="current-task"] button'):lastFocus.current;const fallback=document.querySelector<HTMLElement>('.tutorial-entry');(target?.isConnected?target:fallback)?.focus()};setMode('closed');setPaused(false);manual.current=false}
  catch(e){if(alive.current&&!request.current?.signal.aborted)setError(reportError(e,'教程状态暂未保存'))}
  finally{savingRef.current=false;if(alive.current)setSaving(false)}
 }

 // A tutorial yields to real work, real feedback, and user questions.
 useEffect(()=>{
  if(mode==='closed'){blockedRef.current=false;setBlocked(false);return}
  let priorDialog:HTMLElement|undefined;let focusFrame=0;
  const inspect=()=>{const dialog=[...document.querySelectorAll<HTMLElement>('.operation-error-overlay,.modal-overlay,[role="dialog"][aria-modal="true"],.chat-overlay')].find(el=>!portal.current?.contains(el)&&el.getBoundingClientRect().width>0);const stop=Boolean(dialog)||pendingOperations().some(op=>op.ai);blockedRef.current=stop;setBlocked(stop);if(stop)setPaused(true);if(dialog&&dialog!==priorDialog){cancelAnimationFrame(focusFrame);focusFrame=requestAnimationFrame(()=>{if(!dialog.contains(document.activeElement))dialog.querySelector<HTMLElement>('textarea,input,button')?.focus()})}priorDialog=dialog};
  const observer=new MutationObserver(inspect);observer.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['class','open','aria-modal']});window.addEventListener('operation-progress',inspect);inspect();
  return()=>{cancelAnimationFrame(focusFrame);observer.disconnect();window.removeEventListener('operation-progress',inspect)};
 },[mode]);

 // Lock user-driven page scrolling, while keeping tutorial scrolling and
 // programmatic scrollIntoView for the next spotlight available.
 useEffect(()=>{
  if(!visible)return;
  const surfaces=[document.documentElement,document.body].map(el=>({el,locked:el.classList.contains('tutorial-scroll-lock')}));
  surfaces.forEach(({el})=>el.classList.add('tutorial-scroll-lock'));
  const scrollArea=(target:EventTarget|null)=>{
   if(!(target instanceof Element)||!card.current?.contains(target))return null;
   const copy=target.closest<HTMLElement>('.tutorial-copy');
   if(copy&&copy.scrollHeight>copy.clientHeight+1&&getComputedStyle(copy).overflowY!=='visible')return copy;
   return null;
  };
  const wheel=(event:WheelEvent)=>{if(!event.ctrlKey&&!scrollArea(event.target))event.preventDefault()};
  const touch=(event:TouchEvent)=>{if(event.touches.length===1&&!scrollArea(event.target))event.preventDefault()};
  const key=(event:KeyboardEvent)=>{
   if(event.defaultPrevented||event.ctrlKey||event.metaKey||event.altKey)return;
   if(!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','PageUp','PageDown','Home','End',' '].includes(event.key))return;
   const target=event.target instanceof Element?event.target:null;
   if(target?.closest('input,textarea,select,[contenteditable="true"]')||event.key===' '&&target?.closest('button,a[href]'))return;
   event.preventDefault();
   const area=scrollArea(target)||card.current?.querySelector<HTMLElement>('.tutorial-copy');
   const scroller=area;
   if(!scroller)return;
   const distance=Math.max(40,scroller.clientHeight*.8);
   if(event.key==='Home')scroller.scrollTop=0;
   else if(event.key==='End')scroller.scrollTop=scroller.scrollHeight;
   else if(event.key==='ArrowUp'||event.key==='ArrowDown')scroller.scrollTop+=event.key==='ArrowUp'?-40:40;
   else if(event.key==='PageUp'||event.key==='PageDown'||event.key===' ')scroller.scrollTop+=event.key==='PageUp'||event.key===' '&&event.shiftKey?-distance:distance;
  };
  document.addEventListener('wheel',wheel,{passive:false,capture:true});
  document.addEventListener('touchmove',touch,{passive:false,capture:true});
  window.addEventListener('keydown',key);
  return()=>{surfaces.forEach(({el,locked})=>{if(!locked)el.classList.remove('tutorial-scroll-lock')});document.removeEventListener('wheel',wheel,true);document.removeEventListener('touchmove',touch,true);window.removeEventListener('keydown',key)};
 },[visible]);

 // Background elements are inert only while the tutorial owns the screen.
 useEffect(()=>{
  if(!visible)return;
  const prior=[...document.body.children].filter(el=>el instanceof HTMLElement&&el!==portal.current&&!el.contains(portal.current)).map(el=>({el,inert:el.hasAttribute('inert')}));
  prior.forEach(({el})=>el.setAttribute('inert',''));card.current?.focus();
  const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();end('skipped')}if(e.key==='Tab'){const nodes=card.current?.querySelectorAll<HTMLElement>('button:not([disabled]),a[href],input,select,textarea');if(!nodes?.length){e.preventDefault();card.current?.focus();return}const first=nodes[0],last=nodes[nodes.length-1];if(e.shiftKey&&(document.activeElement===first||document.activeElement===card.current)){e.preventDefault();last.focus()}else if(!e.shiftKey&&(document.activeElement===last||document.activeElement===card.current)){e.preventDefault();first.focus()}}};
  window.addEventListener('keydown',key);
  return()=>{prior.forEach(({el,inert})=>{if(!inert)el.removeAttribute('inert')});window.removeEventListener('keydown',key)};
 },[visible,mode,index,record]);

 // Restore focus only after the background's inert attributes have been removed.
 useEffect(()=>{if(mode!=='closed'||!afterClose.current)return;const finish=afterClose.current;afterClose.current=null;const frame=requestAnimationFrame(()=>{if(alive.current)finish()});return()=>cancelAnimationFrame(frame)},[mode]);
 useEffect(()=>{const update=()=>setViewport({width:window.innerWidth,height:window.visualViewport?.height||window.innerHeight});window.addEventListener('resize',update);window.visualViewport?.addEventListener('resize',update);update();return()=>{window.removeEventListener('resize',update);window.visualViewport?.removeEventListener('resize',update)}},[]);
 useEffect(()=>{if(!visible||!card.current)return;const el=card.current;const measure=()=>{const header=el.querySelector('header'),footer=el.querySelector('footer');setMinimumHeight(Math.ceil((header?.getBoundingClientRect().height||0)+(footer?.getBoundingClientRect().height||0)+160))};const observer=new ResizeObserver(measure);el.querySelectorAll('header,footer').forEach(node=>observer.observe(node));measure();return()=>observer.disconnect()},[visible,mode,index]);

 useEffect(()=>{
  if(mode!=='active'||!visible){setRect(null);return}
  if(step.id==='practice')window.dispatchEvent(new CustomEvent('open-personalized-learning',{detail:{project:scope}}));
  let frame=0;let target:HTMLElement|null=null;const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const find=()=>{const found=step.targets.map(selector=>document.querySelector<HTMLElement>(selector));const position=found.findIndex(el=>el&&el.getBoundingClientRect().width>0);setFallbackTarget(position>0);return found[position]||null};
  const measure=()=>{frame=0;target=find();if(!target){setRect(null);return}const r=target.getBoundingClientRect(),height=window.visualViewport?.height||window.innerHeight;const left=Math.max(8,r.left-8),top=Math.max(8,r.top-8),right=Math.min(window.innerWidth-8,r.right+8),bottom=Math.min(height-8,r.bottom+8);if(right<=left||bottom<=top){setRect(null);return}const value={left,top,right,bottom,width:right-left,height:bottom-top};setRect(old=>old&&Object.keys(value).every(k=>Math.abs(old[k as keyof Rect]-value[k as keyof Rect])<1)?old:value)};
  const schedule=()=>{if(!frame)frame=requestAnimationFrame(measure)};
  target=find();target?.scrollIntoView({block:'center',behavior:reduced?'auto':'smooth'});schedule();
  const observer=new MutationObserver(schedule);observer.observe(document.getElementById('root')!,{childList:true,subtree:true});const resize=new ResizeObserver(schedule);if(target)resize.observe(target);
  window.addEventListener('resize',schedule);window.addEventListener('scroll',schedule,true);window.visualViewport?.addEventListener('resize',schedule);
  return()=>{cancelAnimationFrame(frame);observer.disconnect();resize.disconnect();window.removeEventListener('resize',schedule);window.removeEventListener('scroll',schedule,true);window.visualViewport?.removeEventListener('resize',schedule)};
 },[visible,mode,index,step,scope]);
 useEffect(()=>{if(visible&&mode==='active'){card.current?.scrollTo({top:0});card.current?.querySelector<HTMLElement>('.tutorial-copy')?.scrollTo({top:0});card.current?.focus({preventScroll:true})}},[index,visible,mode]);

 function resume(){if(blocked)return;onPrepare?.();setPaused(false)}
 const width=Math.max(180,Math.min(440,viewport.width-32)),gap=20;let left=(viewport.width-width)/2,top=16,maxHeight=Math.max(80,viewport.height-32),overlayFallback=false;
 if(rect&&viewport.width>=950&&(viewport.width-rect.right>=width+gap+16||rect.left>=width+gap+16)){left=viewport.width-rect.right>=width+gap+16?rect.right+gap:rect.left-width-gap;top=Math.max(16,Math.min(rect.top,viewport.height-minimumHeight-16));maxHeight=Math.max(80,viewport.height-top-16)}
 else if(rect){const above=rect.top-gap-16,below=viewport.height-rect.bottom-gap-16;if(Math.max(above,below)>=minimumHeight){if(above>below){maxHeight=above;top=16}else{top=rect.bottom+gap;maxHeight=below}}else{overlayFallback=true}}
 // Long steps stay near the top; reserve viewport space for the fixed footer.
 if(!rect||overlayFallback)top=16;
 maxHeight=Math.max(0,Math.min(maxHeight,viewport.height-top-16));
 if(mode==='closed')return null;
 return createPortal(<div ref={portal} className="tutorial-root">
  {paused?(!blocked&&<aside className="tutorial-paused"><BookOpen size={19}/><div><strong>使用教程已暂停</strong><p>刚才的操作已经结束。准备好后，可以从原来的步骤继续。</p></div><button className="button secondary" disabled={saving} onClick={resume}>继续教程</button><button aria-label="结束本次教程" disabled={saving} onClick={()=>end('skipped')}><X size={17}/></button></aside>):<>
   <svg className="tutorial-shade" width="100%" height="100%" aria-hidden="true"><defs><mask id={maskId}><rect width="100%" height="100%" fill="white"/>{rect&&<rect x={rect.left} y={rect.top} width={rect.width} height={rect.height} rx="12" fill="black"/>}</mask></defs><rect width="100%" height="100%" fill="rgba(0,0,0,0.72)" mask={'url(#'+maskId+')'}/></svg>
   {rect&&<div className="tutorial-spotlight" style={{left:rect.left,top:rect.top,width:rect.width,height:rect.height}} aria-hidden="true"/>}
   <section ref={card} tabIndex={-1} className={'tutorial-card '+(mode==='welcome'?'tutorial-welcome':'')} style={mode==='active'?{left,top,width,maxHeight}:{maxHeight:Math.max(0,viewport.height-32)}} role="dialog" aria-modal="true" aria-labelledby="tutorial-heading">
    <header><span className="tutorial-label"><BookOpen size={16}/>{scope==='library'?'第一次使用 · 项目库':scope==='retail'?'销售分析 · 使用教程':'软件工程 · 使用教程'}</span><button className="tutorial-close" aria-label="跳过教程" disabled={saving} onClick={()=>end('skipped')}><X size={19}/></button><h2 id="tutorial-heading">{mode==='welcome'?record?.status==='in_progress'?'接着上次的教程继续':'一步一步，找到接下来怎么做':step.title}</h2>{mode==='active'&&<p className="tutorial-counter">第 {index+1} / {steps.length} 步</p>}</header>
    <div className="tutorial-copy">
     {loading?<p role="status">正在读取这个账号的教程进度…</p>:mode==='welcome'?<><p>{scope==='library'?'先认识专业筛选、项目要求和进入按钮。然后由你自己选择一个实训。':'我们会先打开你当前已解锁的任务，再介绍材料、提交、反馈和求助入口。'}</p><p>每一步会分别说明这个区域是什么、你要怎样操作，以及完成后看哪里。遇到概念或缩写，会在本步解释。</p><p>现在先阅读教程，用说明卡上的「下一步」继续；背景页面的按钮在引导期间暂时不能点击。完成或跳过教程后，再按照说明操作页面。</p><p>教程不会替你作答或提交文件。你可以用「上一步」重看，也可以跳过；之后在「使用教程」中重新打开。</p>{record?.status==='in_progress'&&<p className="tutorial-result">上次停在第 {record.step+1} 步。可以从这里继续，或从第一步重新看。</p>}</>:<><div className="tutorial-explanation">{step.explanation.map(text=><p key={text}>{text}</p>)}</div><h3>你要怎样操作</h3><ol>{step.actions.map(text=><li key={text}>{text}</li>)}</ol><div className="tutorial-terms"><h3>这些词在这里是什么意思</h3><dl>{step.terms.map(term=><div key={term.name}><dt>{term.name}</dt><dd>{term.meaning}</dd></div>)}</dl></div><div className="tutorial-result"><h3>完成后看什么</h3><p>{step.result}</p></div>{(!rect||fallbackTarget)&&<p className="tutorial-location-note">{step.id==='feedback'?'当前没有「查看本次反馈」入口。光圈标出本页结果所在区域；如已有检查结果，请在这里阅读，否则先完成首次提交。':step.id==='practice'?'当前还没有可用的练习安排按钮。请先完成起点诊断；独立测评期间也会暂停针对答案的练习。':'本步的具体操作入口目前尚未显示，光圈可能只标出所在区域。请先阅读说明；满足本页前序要求后，再使用对应入口。'}</p>}{overlayFallback&&<p className="tutorial-location-note">当前屏幕没有足够空间同时显示完整说明和聚焦区域。请在说明卡内向下滚动，读完后点击「下一步」；结束教程后再操作页面。</p>}</>}
     {error&&<div role="alert" className="alert">{error}{!record&&<button className="text-link" onClick={()=>load()}>重新读取教程</button>}</div>}
    </div>
    <footer>{saving?<span role="status" className="tutorial-saving"><LoaderCircle size={16}/>正在保存教程位置…</span>:<span>可以逐步阅读，不需要一次记住全部。</span>}<div className="tutorial-actions">
     {mode==='welcome'?<><button className="button secondary" disabled={saving||loading} onClick={()=>end('skipped')}>稍后再看</button>{record?.status==='in_progress'&&<button className="text-link" disabled={saving||loading} onClick={()=>begin(true)}>从第一步开始</button>}<button className="button" disabled={saving||loading||!record} onClick={()=>begin()}>{record?.status==='in_progress'?'继续上次教程':'开始引导'}<ArrowRight size={15}/></button></>:<><button className="button secondary" disabled={saving||index===0} onClick={()=>move(index-1)}><ArrowLeft size={15}/>上一步</button><button className="text-link" disabled={saving} onClick={()=>end('skipped')}>跳过</button><button className="button" disabled={saving} onClick={()=>index===steps.length-1?end('completed'):move(index+1)}>{index===steps.length-1?scope==='library'?'完成，去选择项目':context?.finished?'完成，查看我的作品':'完成，开始当前任务':'下一步'}{index===steps.length-1?<Check size={15}/>:<ArrowRight size={15}/>}</button></>}
    </div></footer>
   </section>
  </>}
 </div>,document.body);
}
