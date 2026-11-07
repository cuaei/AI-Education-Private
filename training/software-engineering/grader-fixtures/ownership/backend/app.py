"""Original fictional training application; A implementation."""
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

ROOT=Path(__file__).resolve().parents[1]
DB=Path(os.environ.get('TRAINING_DB','/tmp/activity-training.sqlite'))
app=FastAPI(title='校园活动报名')

def connect():
    db=sqlite3.connect(DB,timeout=15,isolation_level=None)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=15000')
    return db

def initialize():
    db=connect()
    try:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE,role TEXT);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS activities(id INTEGER PRIMARY KEY,owner INTEGER REFERENCES users(id),title TEXT,capacity INTEGER,deadline TEXT,starts_at TEXT);
        CREATE TABLE IF NOT EXISTS registrations(id INTEGER PRIMARY KEY AUTOINCREMENT,activity_id INTEGER REFERENCES activities(id),student_id INTEGER REFERENCES users(id),status TEXT,sequence INTEGER);
        ''')
        for i,name in enumerate(['student1','student2','student3','student4','organizer','organizer2'],1):
            db.execute('INSERT OR IGNORE INTO users VALUES(?,?,?)',(i,name,'organizer' if name.startswith('organizer') else 'student'))
        db.execute('INSERT OR IGNORE INTO activities VALUES(1,5,?,2,?,?)',('AI校园开放日','2099-10-08T12:00:00+00:00','2099-10-09T12:00:00+00:00'))
    finally:db.close()

initialize()

def instant(text):
    try:
        result=datetime.fromisoformat(text.replace('Z','+00:00'))
        if result.tzinfo is None:raise ValueError()
        return result.astimezone(timezone.utc)
    except (ValueError,TypeError,AttributeError):raise HTTPException(422,'时间必须包含时区。')

def now():
    return instant(os.environ.get('COURSE_CLOCK','2099-10-01T00:00:00+00:00'))

def identity(request,db):
    user=db.execute('SELECT users.* FROM sessions JOIN users ON sessions.user_id=users.id WHERE token=?',(request.cookies.get('activity_session',''),)).fetchone()
    if not user:raise HTTPException(401,'请先登录。')
    return dict(user)

def activity(db,aid):
    row=db.execute('SELECT * FROM activities WHERE id=?',(aid,)).fetchone()
    if not row:raise HTTPException(404,'活动不存在。')
    return dict(row)

def view(db,row):
    out=dict(row)
    count=db.execute("SELECT COUNT(*) FROM registrations WHERE activity_id=? AND status='confirmed'",(out['id'],)).fetchone()[0]
    return {**out,'registered':count,'remaining':out['capacity']-count,'closed':now()>=instant(out['deadline'])}

class Login(BaseModel):
    username:str
    password:str

class ActivityInput(BaseModel):
    title:str=Field(min_length=1,max_length=100)
    capacity:int=Field(gt=0,le=1000,strict=True)
    deadline:str
    starts_at:str

class JoinInput(BaseModel):
    waitlist:bool=False

@app.post('/api/auth/login')
def login(payload:Login):
    db=connect()
    try:
        user=db.execute('SELECT * FROM users WHERE username=?',(payload.username,)).fetchone()
        if not user or payload.password!='Demo2026!':raise HTTPException(401,'虚构训练账号或密码错误。')
        token=secrets.token_urlsafe(24);db.execute('INSERT INTO sessions VALUES(?,?)',(token,user['id']))
        response=JSONResponse(dict(user));response.set_cookie('activity_session',token,httponly=True,samesite='strict');return response
    finally:db.close()

@app.get('/api/activities')
def activities():
    db=connect()
    try:return [view(db,r) for r in db.execute('SELECT * FROM activities ORDER BY id')]
    finally:db.close()

@app.get('/api/activities/{aid}')
def details(aid:int):
    db=connect()
    try:return view(db,activity(db,aid))
    finally:db.close()

@app.post('/api/activities')
def create_activity(payload:ActivityInput,request:Request):
    db=connect()
    try:
        user=identity(request,db)
        if user['role']!='organizer':raise HTTPException(403,'只有组织者可以发布。')
        if instant(payload.deadline)>instant(payload.starts_at):raise HTTPException(422,'截止时间不能晚于开始时间。')
        cursor=db.execute('INSERT INTO activities(owner,title,capacity,deadline,starts_at) VALUES(?,?,?,?,?)',(user['id'],payload.title.strip(),payload.capacity,payload.deadline,payload.starts_at))
        return view(db,activity(db,cursor.lastrowid))
    finally:db.close()

@app.post('/api/activities/{aid}/register')
def register(aid:int,payload:JoinInput,request:Request):
    db=connect()
    try:
        db.execute('BEGIN IMMEDIATE')
        user=identity(request,db)
        if user['role']!='student':raise HTTPException(403,'组织者不能以学生身份报名。')
        event=activity(db,aid)
        if now()>=instant(event['deadline']):raise HTTPException(409,'报名已截止。')
        existing=db.execute("SELECT * FROM registrations WHERE activity_id=? AND student_id=? AND status IN ('confirmed','waiting')",(aid,user['id'])).fetchone()
        if existing:
            db.commit();return dict(existing)
        count=db.execute("SELECT COUNT(*) FROM registrations WHERE activity_id=? AND status='confirmed'",(aid,)).fetchone()[0]
        if count>=event['capacity']:raise HTTPException(409,'活动名额已满。')
        status='confirmed'
        cursor=db.execute('INSERT INTO registrations(activity_id,student_id,status,sequence) VALUES(?,?,?,NULL)',(aid,user['id'],status))
        db.execute('UPDATE registrations SET sequence=id WHERE id=?',(cursor.lastrowid,))
        row=dict(db.execute('SELECT * FROM registrations WHERE id=?',(cursor.lastrowid,)).fetchone())
        db.commit();return row
    except Exception:
        db.rollback();raise
    finally:db.close()

@app.get('/api/registrations/mine')
def mine(request:Request):
    db=connect()
    try:
        user=identity(request,db)
        return [dict(r) for r in db.execute('SELECT registrations.*,activities.title FROM registrations JOIN activities ON activities.id=registrations.activity_id WHERE student_id=? ORDER BY registrations.id',(user['id'],))]
    finally:db.close()

@app.post('/api/registrations/{rid}/cancel')
def cancel(rid:int,request:Request):
    db=connect()
    try:
        db.execute('BEGIN IMMEDIATE')
        user=identity(request,db)
        row=db.execute('SELECT * FROM registrations WHERE id=?',(rid,)).fetchone()
        if not row:raise HTTPException(404,'报名不存在。')
        event=activity(db,row['activity_id'])
        if now()>=instant(event['deadline']):raise HTTPException(409,'截止后不能取消。')
        old_status=row['status']
        if old_status!='cancelled':
            db.execute("UPDATE registrations SET status='cancelled' WHERE id=?",(rid,))
        result=dict(db.execute('SELECT * FROM registrations WHERE id=?',(rid,)).fetchone())
        db.commit();return result
    except Exception:
        db.rollback();raise
    finally:db.close()

@app.get('/api/activities/{aid}/roster')
def roster(aid:int,request:Request):
    db=connect()
    try:
        user=identity(request,db);event=activity(db,aid)
        if user['role']!='organizer' or event['owner']!=user['id']:raise HTTPException(403,'只能查看自己活动名单。')
        return [dict(r) for r in db.execute('SELECT registrations.*,users.username FROM registrations JOIN users ON users.id=registrations.student_id WHERE activity_id=? ORDER BY sequence',(aid,))]
    finally:db.close()

@app.get('/{path:path}')
def frontend(path:str):
    folder=ROOT/'frontend'/'dist';target=(folder/path).resolve()
    if path.startswith('api/'):raise HTTPException(404,'接口不存在。')
    if target.is_relative_to(folder) and target.is_file():return FileResponse(target)
    return FileResponse(folder/'index.html')
