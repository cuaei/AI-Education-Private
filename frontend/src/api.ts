// UUID v4 from secure random bytes; getRandomValues also works on HTTP origins.
export function createId():string{
 const bytes=crypto.getRandomValues(new Uint8Array(16));
 bytes[6]=(bytes[6]&0x0f)|0x40;
 bytes[8]=(bytes[8]&0x3f)|0x80;
 const hex=Array.from(bytes,byte=>byte.toString(16).padStart(2,'0')).join('');
 return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
export type Obj=Record<string,any>;
export type Feedback={id:string;project:string;title:string;message?:string;grade?:Obj;version?:string;type?:string};
export type Operation={id:string;label:string;ai:boolean;started:number};
const pending=new Map<string,Operation>();
export function pendingOperations(){return [...pending.values()]}
function progress(){window.dispatchEvent(new CustomEvent('operation-progress',{detail:pendingOperations()}))}
export function trackOperation(label:string,ai=false){const id=createId();pending.set(id,{id,label,ai,started:Date.now()});progress();return()=>{if(pending.delete(id))progress()}}
export function notifyUser(message:string,title='请检查填写内容',kind:'error'|'info'='error'){
 window.dispatchEvent(new CustomEvent('operation-notice',{detail:{id:createId(),message,title,kind}}));
}
export function reportError(error:unknown,title='操作未完成'){
 const message=error instanceof SyntaxError?'输入的JSON格式不正确。请检查引号、逗号和括号；字段名及文字必须使用双引号。':error instanceof Error?error.message:'操作暂未完成，请稍后重试。';
 if(!(error as any)?.notified)notifyUser(message,title);
 return message;
}
function visibleError(message:string){const error=new Error(message) as Error&{notified:boolean};notifyUser(message,'操作未完成');error.notified=true;return error}
function validationMessage(data:Obj){
 if(typeof data.detail==='string')return data.detail;
 if(Array.isArray(data.detail))return data.detail.map((d:Obj)=>`${(d.loc||[]).filter((s:string)=>!['body','query','path'].includes(s)).join(' / ')||'填写内容'}：${({missing:'此项必须填写',int_parsing:'请输入整数',float_parsing:'请输入数字',string_type:'请输入文字',bool_type:'请选择有效选项'} as Obj)[d.type]||'格式或取值不符合要求，请检查。'}`).join('；');
 return '请求格式不正确，请检查填写内容。';
}
function operationLabel(path:string,body?:unknown):{label:string;ai:boolean}{
 const payload=body as Obj|undefined;
 if(path.startsWith('/teacher/')&&path.endsWith('/plan'))return {label:payload?.use_ai===false?'正在保存教师补练草案…':'AI正在读取学生证据并提出补练草案…',ai:payload?.use_ai!==false};
 if(path.startsWith('/teacher/')&&path.endsWith('/insights'))return {label:'AI正在整理班级共性问题和教学建议…',ai:true};
 if(path.includes('/learning/plan'))return {label:payload?.basic?'正在准备基础练习…':'AI正在分析错误并安排练习…',ai:!payload?.basic};
 if(path.endsWith('/explanation'))return {label:'AI正在读取作答并组织解释…',ai:true};
 if(path.startsWith('/learning/chat/'))return {label:'AI正在读取你的问题并解答…',ai:true};
 if(path.endsWith('/coach')||path==='/coach')return {label:'AI正在读取当前任务并生成反馈…',ai:true};
 if(path.includes('/probes/'))return {label:'正在保存并检查计算步骤…',ai:false};
 if(path.endsWith('/attempts'))return {label:'正在核验你的答案…',ai:false};
 if(path.includes('/auth/'))return {label:path.includes('login')?'正在登录…':path.includes('register')?'正在创建账号…':'正在退出…',ai:false};
 if(path.includes('/upload'))return {label:'正在上传材料，请等待处理完成…',ai:false};
 return {label:'正在保存或检查本次操作…',ai:false};
}
function emitFeedback(path:string,data:Obj){
 const project=path.startsWith('/projects/software-engineering')?'software-engineering':'retail';
 if(path.endsWith('/attempts')&&data.attempt&&!data.attempt.passed){const exercise=data.exercises?.find((e:Obj)=>e.attempts.some((a:Obj)=>a.attempt_id===data.attempt.attempt_id));window.dispatchEvent(new CustomEvent('training-feedback',{detail:{id:createId(),project,title:'这道练习还未通过',message:'答案尚不符合题目要求。请检查单位、计算步骤或情境规则；可查看提示或请AI解释。',grade:{score:0,max_score:1,checks:[{key:exercise?.skill_id,label:exercise?.question||'本次练习',passed:false,weight:1,actual:'本次答案未通过服务端核验，请修改后重交。'}]}}}));}
 let grade:Obj|undefined;
 const quizGrade=(q:Obj)=>({...q,max_score:q.max_score??q.total,checks:q.checks??q.correct?.map((ok:boolean,i:number)=>({key:'quiz-'+i,label:'第'+(i+1)+'题',passed:ok,weight:1,actual:ok?'作答正确。':'本题未符合课程知识要求，可请Agent解释对应概念。'}))});
 if(path==='/diagnostic')grade=quizGrade(data.diagnostic);
 if(path==='/projects/software-engineering/diagnostic')grade=data.diagnostic;
 if(path==='/projects/software-engineering/posttest')grade=data.posttest;
 if(path==='/submit/clean')grade=data.grades?.clean;
 if(path==='/submit/metrics'||path==='/submit/metrics-file')grade=data.grades?.metrics;
 if(path==='/submit/groups')grade=data.grades?.groups;
 if(path==='/transfer'){grade=data.transfer?.evaluation;const q=data.transfer?.posttest;if(q&&q.score<q.total&&grade?.passed)grade=quizGrade(q);}
 if(path.startsWith('/remediation/')||path.startsWith('/projects/software-engineering/practice/')){const id=path.split('/').at(-1);const item=data.remediation?.find((r:Obj)=>r.id===id);if(item&&!item.completed)grade={score:0,max_score:1,checks:[{key:id,label:'本次补练',passed:false,weight:1,actual:'答案尚不正确。请查看知识卡，或请Agent分步解释。'}]};}
 if(path==='/coach'&&data.status==='ok')return; // Review scores arrive with refreshed state, below.
 if(grade?.checks)grade={...grade,checks:grade.checks.map((c:Obj)=>({...c,weight:c.weight??grade!.max_score/grade!.checks.length,actual:c.actual||(c.passed?'符合课程规则。':c.key==='duplicates'?'完全重复行仍未去除。':c.key==='isolated'?'仍存在无效或冲突记录，请查看具体行信息。':c.key==='orders'?'有效订单集合不完整，请检查误删或额外补造的订单。':c.key==='values'?'有效记录字段与原始数据不一致，请保留原始金额、数量及日期。':'此项尚未符合计算或分组口径。请检查退款处理、百分数单位和比较窗口，可请Agent分步解释。')}))};
 if(grade&&grade.score<grade.max_score)window.dispatchEvent(new CustomEvent('training-feedback',{detail:{id:createId(),project,title:'本次得分未满',grade}}));
}
export async function api(path:string,body?:unknown,method?:string,signal?:AbortSignal):Promise<any>{
 const form=body instanceof FormData;const verb=method||(body!==undefined?'POST':'GET');
 const id=createId(),controller=new AbortController();let timedOut=false;
 const cancel=()=>controller.abort();if(signal?.aborted)cancel();else signal?.addEventListener('abort',cancel,{once:true});
 const timer=setTimeout(()=>{timedOut=true;controller.abort()},300000);
 const options:RequestInit={method:verb,signal:controller.signal,credentials:'same-origin',headers:{...(form?{}:{'Content-Type':'application/json'}),...(verb==='POST'&&!path.startsWith('/auth/')?{'Idempotency-Key':id}:{})},body:body===undefined?undefined:form?body:JSON.stringify(body)};
 if(verb!=='GET'&&!path.startsWith('/tutorial/')){pending.set(id,{id,...operationLabel(path,body),started:Date.now()});progress()}
 try{
  let r:Response;
  try{r=await fetch('/api'+path,options)}catch(e){if(controller.signal.aborted)throw e;r=await fetch('/api'+path,options)}
  let data:Obj;try{data=await r.json()}catch{throw new Error('服务器没有返回完整结果。请稍后重试；已提交的内容可能已经保存。')}
  if(!r.ok)throw new Error(validationMessage(data));
  const run=data.run||(data.mode==='ai'&&typeof data.status==='string'?data:null);
  if(run&&run.status!=='ok')notifyUser(run.message||'AI未完成此次操作，请重试或使用基础练习。','AI暂未完成');
  else if(run?.needs_human_review)notifyUser(run.message||'AI建议人工复核，请查看本次反馈。','需要进一步确认','info');
  else if(data.learning_outcome)notifyUser(data.learning_outcome.message,'练习安排',data.learning_outcome.type==='error'?'error':'info');
  if(verb==='POST')emitFeedback(path,data);return data;
 }catch(e){
  if(signal?.aborted)throw e;
  if(path==='/me'&&verb==='GET')throw e;
  const message=timedOut?'等待已超过5分钟。你填写的内容仍保留在页面；服务端可能仍在处理，请先查看记录再重试。':e instanceof TypeError?'无法连接服务器，请检查网络或本机服务是否运行。':e instanceof Error?e.message:'操作失败，请稍后重试。';
  throw visibleError(message);
 }finally{clearTimeout(timer);signal?.removeEventListener('abort',cancel);if(pending.delete(id))progress()}
}
