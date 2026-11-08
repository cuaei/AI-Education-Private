import BrandMark from './BrandMark';
import {useEffect,useRef,useState,type FormEvent} from 'react';
import {ArrowLeft,ArrowRight,Check,Eye,EyeOff,FileChartColumn,MessageCircle,UserPlus} from 'lucide-react';
import {notifyUser,trackOperation} from './api';

type Field='username'|'password'|'confirmation';
type FieldErrors=Partial<Record<Field,string>>;

export default function Registration({onBack,onSuccess}:{onBack:()=>void;onSuccess:(username:string)=>void}){
 const [username,setUsername]=useState(''),[password,setPassword]=useState(''),[confirmation,setConfirmation]=useState('');
 const [visible,setVisible]=useState(false),[busy,setBusy]=useState(false),[errors,setErrors]=useState<FieldErrors>({}),[message,setMessage]=useState('');
 const usernameInput=useRef<HTMLInputElement>(null),passwordInput=useRef<HTMLInputElement>(null),confirmationInput=useRef<HTMLInputElement>(null);
 const submitting=useRef(false),controller=useRef<AbortController|null>(null),mounted=useRef(true);
 useEffect(()=>{mounted.current=true;window.scrollTo({top:0,behavior:'auto'});usernameInput.current?.focus();return()=>{mounted.current=false;controller.current?.abort()}},[]);
 function focus(field:Field){({username:usernameInput,password:passwordInput,confirmation:confirmationInput})[field].current?.focus()}
 function update(field:Field,value:string){({username:setUsername,password:setPassword,confirmation:setConfirmation})[field](value);setErrors(e=>({...e,[field]:undefined}));setMessage('')}
 async function submit(event:FormEvent){
  event.preventDefault();if(submitting.current)return;
  const name=username.trim(),invalid:FieldErrors={};
  if(!/^[A-Za-z0-9_-]{3,30}$/.test(name))invalid.username='请输入 3–30 位英文字母、数字、底线或连字号。';
  const length=Array.from(password).length;
  if(length<10||length>200||!password.trim())invalid.password='密码需为 10–200 个字符，不能全为空白。';
  if(!confirmation||password!==confirmation)invalid.confirmation='请确认两次输入的密码一致。';
  setErrors(invalid);setMessage('');
  const first=(['username','password','confirmation'] as Field[]).find(f=>invalid[f]);if(first){focus(first);notifyUser(invalid[first]||'请检查填写内容。');return}
  submitting.current=true;setBusy(true);const requestController=new AbortController();controller.current=requestController;
  const timeout=window.setTimeout(()=>requestController.abort(),20000);
  const done=trackOperation('正在创建账号…');
  try{
   // Account creation is intentionally sent once, without the API helper's retry.
   const response=await fetch('/api/auth/register',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:name,password,confirm_password:confirmation}),signal:controller.current.signal});
   const result=await response.json().catch(()=>null);
   if(!response.ok){
    const detail=typeof result?.detail==='string'?result.detail:'注册未完成，请检查填写内容后重试。';
    notifyUser(detail,'注册未完成');
    const field:Field|undefined=response.status===409?'username':response.status===422?(detail.includes('两次')?'confirmation':detail.includes('密码')?'password':'username'):undefined;
    if(mounted.current){if(field){setErrors({[field]:detail});focus(field)}else setMessage(detail)}
    return;
   }
   if(!result||typeof result.username!=='string'){if(mounted.current){const detail='无法确认注册结果，请先返回登录，用刚才的账号尝试登录。';setMessage(detail);notifyUser(detail,'注册结果待确认')}return}
   if(mounted.current){setPassword('');setConfirmation('');onSuccess(result.username)}
  }catch{
   if(mounted.current){const detail='连接中断或等待超时，暂时无法确认注册结果。请先返回登录，用刚才的账号尝试登录；若无法登录，再返回这里重试。';setMessage(detail);notifyUser(detail,'注册结果待确认')}
  }finally{done();window.clearTimeout(timeout);controller.current=null;submitting.current=false;if(mounted.current)setBusy(false)}
 }
 return <div className="login-screen registration-screen"><div className="login-story"><div className="brand light"><BrandMark/>我要实习</div><div><h1>给你的第一份作品，<br/>一个开始。</h1><p>创建学生账号，选择你的实训方向。<br/>从任务、修改到交付，保存自己的学习过程。</p><div className="login-art"><div className="art-line"/><span><Check size={22}/>完成任务</span><span><FileChartColumn size={22}/>核验成果</span><span><MessageCircle size={22}/>向教练提问</span></div></div></div><div className="login-form registration-form"><button className="text-link registration-back" type="button" disabled={busy} onClick={onBack}><ArrowLeft size={16}/>返回登录</button><h2><UserPlus size={25}/>注册学生账号</h2><p>注册后返回登录，再选择想体验的实训项目。</p>
 <form onSubmit={submit} noValidate aria-busy={busy}>
  <label htmlFor="register-username">账号<input id="register-username" ref={usernameInput} value={username} onChange={e=>update('username',e.target.value)} autoComplete="username" autoCapitalize="none" spellCheck={false} maxLength={30} required disabled={busy} aria-invalid={Boolean(errors.username)} aria-describedby={'register-username-hint'+(errors.username?' register-username-error':'')}/><small id="register-username-hint" className="auth-field-hint">3–30 位英文字母、数字、底线或连字号，区分大小写。</small>{errors.username&&<span id="register-username-error" className="auth-field-error" role="alert">{errors.username}</span>}</label>
  <label htmlFor="register-password">密码<input id="register-password" ref={passwordInput} type={visible?'text':'password'} value={password} onChange={e=>update('password',e.target.value)} autoComplete="new-password" maxLength={400} required disabled={busy} aria-invalid={Boolean(errors.password)} aria-describedby={'register-password-hint'+(errors.password?' register-password-error':'')}/><small id="register-password-hint" className="auth-field-hint">10–200 个字符，建议组合字母、数字和符号。</small>{errors.password&&<span id="register-password-error" className="auth-field-error" role="alert">{errors.password}</span>}</label>
  <label htmlFor="register-confirmation">确认密码<input id="register-confirmation" ref={confirmationInput} type={visible?'text':'password'} value={confirmation} onChange={e=>update('confirmation',e.target.value)} autoComplete="new-password" maxLength={400} required disabled={busy} aria-invalid={Boolean(errors.confirmation)} aria-describedby={errors.confirmation?'register-confirmation-error':undefined}/>{errors.confirmation&&<span id="register-confirmation-error" className="auth-field-error" role="alert">{errors.confirmation}</span>}</label>
  <button type="button" className="text-link auth-show-password" aria-pressed={visible} disabled={busy} onClick={()=>setVisible(v=>!v)}>{visible?<EyeOff size={16}/>:<Eye size={16}/>} {visible?'隐藏密码':'显示密码'}</button>
  {message&&<div className="alert auth-message" role="alert">{message}</div>}
  <button type="submit" className="button" disabled={busy}>{busy?'正在创建账号…':'注册并返回登录'}<ArrowRight size={17}/></button>
 </form><div className="auth-switch"><span>已经有账号？</span><button type="button" className="text-link" disabled={busy} onClick={onBack}>返回登录<ArrowRight size={14}/></button></div></div></div>;
}
