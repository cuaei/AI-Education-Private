from datetime import datetime, timedelta, timezone
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from fastapi.responses import Response
from fastapi import Depends, HTTPException
from .agent import run_agent

TOPICS = [
 ('java-basic','Java 基础','黑马 Java 基础','BV1TJxCzSEEZ'),('java-advanced','Java 进阶','Java 进阶候选','BV1gb42177hm'),
 ('git','Git 版本管理','黑马 Git 教程','BV1MU4y1Y7h5'),('mysql','MySQL 数据库','黑马 MySQL 教程','BV1Kr4y1i7ru'),
 ('java-web','Java Web','黑马 JavaWeb','BV1yGydYEE3H'),('business-redis','业务项目与 Redis','苍穹外卖','BV1TP411v7v6'),
 ('linux','Linux 基础','尚硅谷 Linux','BV19W4y1w7cM'),('docker','Docker 基础','黑马 Docker 教程','BV1HP4118797'),
 ('testing-security','测试与安全',None,None),
]
def china_day(): return datetime.now(timezone(timedelta(hours=8))).date().isoformat()

def reserve_ai_quota(store, user_id):
    day=china_day()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT OR IGNORE INTO ai_daily_quota VALUES(?,?,0)',(user_id,day))
        cur=db.execute('UPDATE ai_daily_quota SET used=used+1 WHERE user_id=? AND day=? AND used<10',(user_id,day))
        if cur.rowcount!=1: raise HTTPException(429,'今日 AI 次数已用完，明天可继续提问。')
    return day

def mount_java_route(app, store, student):
    with store.connect() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS java_progress(user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, resource_id TEXT NOT NULL, PRIMARY KEY(user_id,resource_id));
        CREATE TABLE IF NOT EXISTS ai_daily_quota(user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, day TEXT NOT NULL, used INTEGER NOT NULL, PRIMARY KEY(user_id,day));
        CREATE TABLE IF NOT EXISTS java_ai_log(id INTEGER PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, day TEXT NOT NULL, question TEXT NOT NULL, result TEXT NOT NULL);''')
    @app.get('/api/java-route/example-starter')
    def example_starter(current=Depends(student)):
        source = Path(__file__).resolve().parents[1] / 'training' / 'java-example'
        output = BytesIO()
        with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
            for name in ('README.md', 'src/Main.java', 'src/CompetitionService.java'):
                archive.writestr(name, (source / name).read_bytes())
        return Response(content=output.getvalue(), media_type='application/zip',
                        headers={'Content-Disposition': 'attachment; filename="java-example-starter.zip"'})

    @app.get('/api/java-route')
    def route(current=Depends(student)):
        with store.connect() as db:
            done=[r['resource_id'] for r in db.execute('SELECT resource_id FROM java_progress WHERE user_id=?',(current['id'],))]
            row=db.execute('SELECT used FROM ai_daily_quota WHERE user_id=? AND day=?',(current['id'],china_day())).fetchone()
        return {'topics':[{'id':i,'title':title,'resource':{'id':i,'title':name,'url':'https://www.bilibili.com/video/'+bv+'/' } if bv else None} for i,title,name,bv in TOPICS], 'completed':done,'remaining':10-(row['used'] if row else 0),'ai_enabled':app.state.model_config.enabled}
    @app.post('/api/java-route/progress')
    def progress(payload:dict,current=Depends(student)):
        rid=payload.get('resource_id');value=payload.get('completed')
        if rid not in {i for i,_,_,bv in TOPICS if bv} or type(value) is not bool: raise HTTPException(422,'学习资料或状态无效。')
        with store.connect() as db:
            if value: db.execute('INSERT OR IGNORE INTO java_progress VALUES(?,?)',(current['id'],rid))
            else: db.execute('DELETE FROM java_progress WHERE user_id=? AND resource_id=?',(current['id'],rid))
        return {'ok':True}
    @app.post('/api/java-route/ask')
    def ask(payload:dict,current=Depends(student)):
        question=payload.get('question')
        if not isinstance(question,str) or not 1<=len(question.strip())<=2000:raise HTTPException(422,'请输入不超过2000字的问题。')
        if not app.state.model_config.enabled:raise HTTPException(503,'AI 尚未配置，请联系管理员。')
        day=reserve_ai_quota(store,current['id'])
        answers=[]
        def answer(args):
            value=args.get('text'); ids=args.get('evidence_ids')
            if not isinstance(value,str) or not 1<=len(value)<=4000 or ids!=[]:raise ValueError('回复格式无效')
            answers.append(value);return {'saved':True}
        context={'question':question.strip(),'purpose':'question','evidence_ids':[],'facts':{},'policy':'面向零基础学生解释Java后端学习概念，不声称读取外部资料或执行程序。'}
        try:
            result=run_agent('question',context,app.state.model_config,{'answer_question':answer})
        except Exception:
            result={'status':'error','mode':'ai','message':'AI 请求失败，可能已产生费用，本次计入次数。'}
        with store.connect() as db:
            db.execute('INSERT INTO java_ai_log(user_id,day,question,result) VALUES(?,?,?,?)',(current['id'],day,question.strip(),json.dumps(result,ensure_ascii=False,default=str)))
        message=answers[-1] if result.get('status')=='ok' and answers else result.get('message','AI 未完成回复，请稍后再试。')
        return {'message':message,'status':result.get('status'),'remaining':route(current)['remaining'],'notice':'AI 请求可能产生费用；失败也计入次数。'}
