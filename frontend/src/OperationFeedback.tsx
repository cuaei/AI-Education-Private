import {useEffect,useRef,useState} from 'react';
import {AlertCircle,CheckCircle2,LoaderCircle,X} from 'lucide-react';
import {pendingOperations,notifyUser,type Operation} from './api';
import './operation-feedback.css';

type Notice={id:string;title:string;message:string;kind:'error'|'info'};
export default function OperationFeedback(){
 const [operations,setOperations]=useState<Operation[]>(pendingOperations),[notices,setNotices]=useState<Notice[]>([]),[now,setNow]=useState(Date.now());
 const notice=notices[0];
 const close=useRef<HTMLButtonElement>(null),previous=useRef<HTMLElement|null>(null),last=useRef({message:'',time:0});
 useEffect(()=>{
  const update=(event:Event)=>{setNow(Date.now());setOperations((event as CustomEvent<Operation[]>).detail)};
  const show=(event:Event)=>{const n=(event as CustomEvent<Notice>).detail;if(last.current.message===n.message&&Date.now()-last.current.time<1000)return;last.current={message:n.message,time:Date.now()};if(!document.activeElement?.closest('.operation-error'))previous.current=document.activeElement as HTMLElement;setNotices(q=>q.some(item=>item.kind===n.kind&&item.message===n.message)?q:n.kind==='error'&&q[0]?.kind==='info'?[n,...q]:[...q,n])};
  const invalid=(event:Event)=>{const field=event.target as HTMLInputElement;const label=field.labels?.[0]?.textContent?.trim()||field.getAttribute('aria-label')||'这项内容';notifyUser(`${label.slice(0,60)}：${field.validationMessage||'请检查填写内容。'}`)};
  window.addEventListener('operation-progress',update);window.addEventListener('operation-notice',show);document.addEventListener('invalid',invalid,true);
  return()=>{window.removeEventListener('operation-progress',update);window.removeEventListener('operation-notice',show);document.removeEventListener('invalid',invalid,true)};
 },[]);
 useEffect(()=>{if(!operations.length)return;const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer)},[operations.length]);
 function dismiss(){setNotices(q=>q.slice(1));previous.current?.isConnected&&previous.current.focus()}
 useEffect(()=>{if(!notice||notice.kind!=='info')return;const timer=setTimeout(()=>setNotices(q=>q[0]?.id===notice.id?q.slice(1):q),12000);return()=>clearTimeout(timer)},[notice?.id]);
 useEffect(()=>{
  if(!notice||notice.kind!=='error')return;close.current?.focus();
  const keyboard=(e:KeyboardEvent)=>{if(e.key==='Escape')dismiss();if(e.key==='Tab'){e.preventDefault();close.current?.focus()}};
  window.addEventListener('keydown',keyboard);return()=>window.removeEventListener('keydown',keyboard);
 },[notice]);
 return <>
  {(operations.length>0||notice?.kind==='info')&&<div className="operation-feedback-stack">
  {operations.length>0&&<aside className={'operation-progress'+(operations.some(op=>op.ai)?' operation-progress-ai':'')} role="status" aria-live="polite">{operations.map(op=>{const seconds=Math.max(0,Math.floor((now-op.started)/1000));return <div key={op.id}><LoaderCircle className="operation-spinner" size={op.ai?30:24} strokeWidth={op.ai?2.5:2}/><div><strong>{op.label}</strong><p aria-live="off">{seconds<15?'请求处理中，请稍候，无需重复点击。':`已等待${seconds}秒，${op.ai?'AI仍在处理，请求较慢时可能需要更久。':'服务器仍在处理。'}`}</p></div></div>})}</aside>}
  {notice?.kind==='info'&&<aside className="operation-info" role="status"><CheckCircle2 size={20}/><div><strong>{notice.title}</strong><p>{notice.message}</p></div><button onClick={dismiss} aria-label="关闭提示"><X size={18}/></button></aside>}
  </div>}
  {notice?.kind==='error'&&<div className="operation-error-overlay"><section className="operation-error" role="alertdialog" aria-modal="true" aria-labelledby="operation-title" aria-describedby="operation-message"><AlertCircle size={28}/><h2 id="operation-title">{notice.title}</h2><p id="operation-message">{notice.message}</p><button ref={close} className="button" onClick={dismiss}>知道了，返回修改</button></section></div>}
 </>;
}
