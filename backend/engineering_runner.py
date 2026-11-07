"""Archive validation and fixed, isolated Docker execution. Never runs uploads on host."""
import ast
import difflib
import hashlib
import io
import json
import os
import secrets
import shutil
import stat
import subprocess
import threading
import time
import zipfile
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parents[1]
COURSE_DIR=ROOT/'training'/'software-engineering'
IMAGE='career-studio-engineering:2026.10.12'
REQUIRED={'backend/app.py','frontend/package.json','frontend/src/main.tsx','frontend/index.html','frontend/tsconfig.json','student_checks.py'}
ALLOWED={'.py','.tsx','.ts','.css','.json','.html','.md','.txt'}
BLOCKED={'node_modules','.venv','venv','dist','.git','__pycache__'}
_previews={};_preview_lock=threading.Lock()

def docker(args,timeout=30,discard_output=False):
    streams={'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL} if discard_output else {'capture_output':True}
    return subprocess.run(['docker',*args],**streams,text=True,encoding='utf-8',errors='replace',timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

def runtime_status():
    if not shutil.which('docker'):return {'available':False,'reason':'未安装Docker；请先安装并启动Docker Desktop。'}
    try:
        r=docker(['image','inspect',IMAGE],15)
        return {'available':r.returncode==0,'image':IMAGE,'reason':'' if r.returncode==0 else '实训运行镜像未准备好，请在项目目录执行 scripts/setup-engineering.ps1。'}
    except (OSError,subprocess.TimeoutExpired):return {'available':False,'reason':'Docker服务尚未就绪。请启动Docker Desktop后再检查。'}

def archive(content,folder):
    if not content or len(content)>5*1024*1024:raise ValueError('源码ZIP不得为空或超过5MB。')
    try:z=zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:raise ValueError('文件不是有效ZIP。请压缩源码目录，勿上传RAR。')
    entries=[i for i in z.infolist() if not i.is_dir()]
    if len(entries)>200 or sum(i.file_size for i in entries)>20*1024*1024:raise ValueError('展开后最多200个文件、20MB。')
    names=[i.filename.replace('\\','/') for i in entries]
    prefix=''
    if names and not all(n in REQUIRED for n in names):
        first=names[0].split('/')[0]
        if all(n.startswith(first+'/') for n in names) and 'backend/app.py' not in names:prefix=first+'/'
    files={};seen=set()
    for info,name in zip(entries,names):
        raw=PurePosixPath(name)
        if raw.is_absolute() or '..' in raw.parts or ':' in name or any(p.startswith('.') for p in raw.parts) or '\x00' in name:raise ValueError('ZIP包含不允许的路径或环境配置：'+name[:100])
        if stat.S_IFMT(info.external_attr>>16) not in (0,stat.S_IFREG):raise ValueError('ZIP只接受普通文件。')
        if any(p in BLOCKED for p in raw.parts) or stat.S_ISLNK(info.external_attr>>16):raise ValueError('不接受依赖目录、链接、构建产物或数据库：'+name[:100])
        path=PurePosixPath(name.removeprefix(prefix));name=path.as_posix()
        if path.suffix.lower() not in ALLOWED or not path.parts or any(p.rstrip(' .').upper().split('.')[0] in {'CON','PRN','AUX','NUL','COM1','LPT1'} for p in path.parts):raise ValueError('不支持的文件：'+name[:100])
        if name.casefold() in seen:raise ValueError('ZIP存在重复或大小写冲突路径：'+name)
        seen.add(name.casefold())
        try:files[name]=z.read(info).decode('utf-8-sig')
        except (UnicodeError,RuntimeError,zipfile.BadZipFile):raise ValueError('源码须为UTF-8且ZIP不可加密：'+name)
    if not REQUIRED.issubset(files):raise ValueError('缺少必需文件：'+', '.join(sorted(REQUIRED-set(files))))
    # Fixed dependencies only; don't execute submitted npm lifecycle scripts.
    try:
        package=json.loads(files['frontend/package.json'])
        fixed=json.loads((COURSE_DIR/'reference/frontend/package.json').read_text(encoding='utf-8'))
        if package.get('dependencies')!=fixed['dependencies'] or package.get('devDependencies')!=fixed['devDependencies']:raise ValueError()
    except (ValueError,AttributeError):raise ValueError('请保留课程规定的前端依赖及版本；平台不安装上传包指定的新依赖。')
    digest=hashlib.sha256(json.dumps(files,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    folder.mkdir(parents=True,exist_ok=True)
    for name,text in files.items():
        dest=(folder/name).resolve()
        if not dest.is_relative_to(folder.resolve()):raise ValueError('源码路径越界。')
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text,encoding='utf-8',newline='\n')
    return digest,sorted(files)

def read_source(submission,path,start=1,end=160):
    if not submission or path not in submission['files']:raise ValueError('该文件不属于当前提交。')
    if type(start)is not int or type(end)is not int or not 1<=start<=end or end-start>199:raise ValueError('一次只能读取最多200行。')
    folder=Path(submission['archive_path']);file=(folder/path).resolve()
    if not file.is_relative_to(folder.resolve()):raise ValueError('文件越界。')
    lines=file.read_text(encoding='utf-8').splitlines()
    return {'path':path,'hash':submission['hash'],'version':submission['version'],'start':start,'end':min(end,len(lines)),'text':'\n'.join(f'{i+1}: {line}' for i,line in enumerate(lines[start-1:end],start-1)),'evidence_ids':[f"source:{submission['hash']}:{path}:{start}-{min(end,len(lines))}"]}

def diff(previous,current,path):
    after=read_source(current,path,1,200)['text']
    before=read_source(previous,path,1,200)['text'] if previous and path in previous['files'] else ''
    return '\n'.join(difflib.unified_diff(before.splitlines(),after.splitlines(),fromfile='上一版本',tofile='当前版本',lineterm=''))[:20000]

def flags(memory='512m'):
    return ['--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--cpus=2','--memory='+memory,'--pids-limit=128','--log-driver=json-file','--log-opt=max-size=1m','--log-opt=max-file=2','--tmpfs','/tmp:rw,nosuid,nodev,size=256m,mode=1777','--user','10001:10001']

def app_args(name,folder,network='none',extra=None):
    return ['run','-d','--name',name,*flags(),'--network',network,'--mount',f'type=bind,source={folder.resolve()},target=/submission,readonly', '-e','COURSE_CLOCK=2099-10-01T00:00:00+00:00',*(extra or []),IMAGE]

def safe_log(text):
    # Output is untrusted and may contain credentials; only fictional application details allowed.
    import re
    text=re.sub(r'(?i)(api[_-]?key|authorization|password|token)\s*[:=]\s*\S+',r'\1=[已隐藏]',text)
    return text[-10000:]

def check_submission(submission,kind,job_id):
    status=runtime_status()
    if not status['available']:return {'status':'environment_failed','message':status['reason']}
    app_name='cs-app-'+secrets.token_hex(6);judge_name='cs-check-'+secrets.token_hex(6)
    started=time.monotonic();log=''
    try:
        r=docker(app_args(app_name,Path(submission['archive_path'])))
        if r.returncode:raise RuntimeError('无法创建隔离运行环境：'+safe_log(r.stderr))
        args=['run','--name',judge_name,*flags('768m'),'--network','container:'+app_name,'--mount',f'type=bind,source={COURSE_DIR.resolve()},target=/checks,readonly','-e','CHECK_KIND='+kind,IMAGE,'python','/checks/checker.py']
        r=docker(args,120)
        log=safe_log(docker(['logs','--tail','120',app_name],10).stdout)
        try:payload=json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError,IndexError):raise RuntimeError('未取得可信检查结果。'+safe_log(r.stderr))
        if r.returncode or payload.get('environment_error'):return {'status':'environment_failed','message':payload.get('environment_error','运行环境失败'),'log':log}
        checks=payload['checks']
        if kind=='A':checks.extend(student_regression(submission,started+120))
        score=sum(c['weight'] for c in checks if c['passed'])
        return {'status':'completed','message':'真实检查已完成。','log':log,'grade':{'job_id':job_id,'hash':submission['hash'],'version':submission['version'],'course_version':'se-2026.10.12.1','score':score,'max_score':60 if kind=='A' else 20,'passed':all(c['passed'] for c in checks),'checks':checks,'source':'runtime','elapsed_ms':round((time.monotonic()-started)*1000)}}
    except subprocess.TimeoutExpired:return {'status':'timeout','message':'运行超过时限，请检查构建、死循环或无法完成的请求。','log':log}
    except (OSError,RuntimeError,KeyError) as e:return {'status':'environment_failed','message':safe_log(str(e)),'log':log}
    finally:
        for name in (judge_name,app_name):
            try:docker(['rm','-f',name],15)
            except Exception:pass

def student_regression(submission,deadline):
    """Untrusted probe runs separately; trusted caller records exit/timeout, not stdout."""
    script=Path(submission['archive_path'])/'student_checks.py'
    try:tree=ast.parse(script.read_text(encoding='utf-8'));has_checks=sum(isinstance(n,ast.Assert) for n in ast.walk(tree))>=3
    except (SyntaxError,UnicodeError):has_checks=False
    result=[]
    # The oracle fixtures are not accessible from the student probe container.
    fixture_root=COURSE_DIR/'grader-fixtures'
    for variant,weight in [('correct',4),('duplicate',2),('capacity',2),('ownership',2)]:
        label={'correct':'学生回归对正确实现不误报','duplicate':'学生回归能发现重复报名故障','capacity':'学生回归能发现容量故障','ownership':'学生回归能发现越权故障'}[variant]
        name='cs-oracle-'+secrets.token_hex(5);probe='cs-probe-'+secrets.token_hex(5);passed=False;actual='student_checks.py至少需要三个实际断言。'
        if has_checks:
            try:
                if time.monotonic()>=deadline:raise subprocess.TimeoutExpired('regression',120)
                r=docker(app_args(name,fixture_root/variant))
                if r.returncode:raise RuntimeError('无法运行回归基准')
                # Trustworthy readiness check runs before the student's script.
                ready=docker(['exec',name,'python','-c',"import httpx,time\nfor i in range(80):\n try:\n  r=httpx.get('http://127.0.0.1:8080/api/activities');r.raise_for_status();break\n except Exception:time.sleep(.5)\nelse:raise SystemExit(2)"],max(1,min(55,deadline-time.monotonic())))
                if ready.returncode:raise RuntimeError('回归基准未启动')
                args=['run','--name',probe,*flags(),'--network','container:'+name,'--mount',f'type=bind,source={script.resolve()},target=/probe.py,readonly',IMAGE,'python','/probe.py']
                ran=docker(args,max(1,min(20,deadline-time.monotonic())),discard_output=True);passed=(ran.returncode==0) if variant=='correct' else (ran.returncode==1)
                actual=f'学生测试实际退出码{ran.returncode}；'+('正确版本应通过。' if variant=='correct' else '故障版本应触发断言失败。')
            except subprocess.TimeoutExpired:actual='学生测试超时，不能算作发现故障。'
            except (OSError,RuntimeError):actual='回归基准环境不可用，本项尚未完成。';raise RuntimeError(actual)
            finally:
                for container in (probe,name):
                    try:docker(['rm','-f',container],10)
                    except Exception:pass
        result.append({'key':'A-REGRESSION-'+variant.upper(),'label':label,'dimension':'regression','weight':weight,'passed':passed,'expected':label,'actual':actual,'source':'runtime'})
    if result and not any(r['passed'] for r in result[1:]):
        result[0].update(passed=False,actual='测试未实际发现任何预设故障，不能仅凭退出0认定回归有效；请确保断言函数被执行。')
    return result

def stop_preview(token):
    with _preview_lock:item=_previews.pop(token,None)
    if item:
        for args in (['rm','-f',item['container']],['network','rm',item['network']]):
            try:docker(args,15)
            except Exception:pass

def start_preview(uid,submission):
    status=runtime_status()
    if not status['available']:raise ValueError(status['reason'])
    with _preview_lock:old=[k for k,v in _previews.items() if v['uid']==uid]
    for token in old:stop_preview(token)
    token=secrets.token_hex(6);name='cs-preview-'+token;network='cs-preview-net-'+token
    item={'uid':uid,'container':name,'network':network,'hash':submission['hash'],'expires':time.time()+1200}
    try:
        r=docker(['network','create','--internal',network])
        if r.returncode:raise ValueError('预览网络不可用。')
        r=docker(app_args(name,Path(submission['archive_path']),network,['-p','127.0.0.2::8080']))
        if r.returncode:raise ValueError('预览未能启动。')
        port=docker(['port',name,'8080/tcp']).stdout.strip().rsplit(':',1)[-1]
        if not port.isdigit():raise ValueError('未分配预览端口。')
        with _preview_lock:_previews[token]=item
        timer=threading.Timer(1200,stop_preview,args=[token]);timer.daemon=True;timer.start()
        return {'url':f'http://127.0.0.2:{port}','hash':submission['hash'],'expires':item['expires'],'message':'独立虚构应用正在启动，请稍候刷新预览；20分钟后销毁。'}
    except Exception:
        with _preview_lock:_previews[token]=item
        stop_preview(token);raise

def stop_user_previews(uid):
    with _preview_lock:tokens=[t for t,v in _previews.items() if v['uid']==uid]
    for token in tokens:stop_preview(token)
