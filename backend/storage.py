"""SQLite persistence, resource ownership, and revocable server-side sessions."""
import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from contextlib import contextmanager


def initial_state():
    return {'revision':0,'data_revision':0,'diagnostic':None,'diagnostic_form':'C','submissions':[],'grades':{'clean':None,'metrics':None,'groups':None},'metrics':{},'tables':{},'remediation':[],'report':None,'report_stale':False,'report_review':None,'defense':[],'defense_snapshot':None,'defense_review':None,'transfer':None,'feedback':[],'agent_runs':[],'human_reviews':[],'portfolio_note':'','next_task':'起点诊断'}


def password_hash(password,salt=None):
    salt=salt or secrets.token_hex(16)
    digest=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
    return salt+':'+digest


class Store:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.user_locks={}
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE,password TEXT,role TEXT,is_demo INTEGER,created REAL);
            CREATE TABLE IF NOT EXISTS states(user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,body TEXT);
            CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id) ON DELETE CASCADE,expires REAL);
            CREATE TABLE IF NOT EXISTS shares(token TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id) ON DELETE CASCADE,body TEXT);
            CREATE TABLE IF NOT EXISTS operations(user_id TEXT REFERENCES users(id) ON DELETE CASCADE,operation_key TEXT,fingerprint TEXT,body BLOB,status INTEGER,media_type TEXT,PRIMARY KEY(user_id,operation_key));
            CREATE TABLE IF NOT EXISTS project_states(user_id TEXT REFERENCES users(id) ON DELETE CASCADE,project_id TEXT,body TEXT,PRIMARY KEY(user_id,project_id));
            CREATE TABLE IF NOT EXISTS learning_states(user_id TEXT REFERENCES users(id) ON DELETE CASCADE,project_id TEXT,body TEXT,PRIMARY KEY(user_id,project_id));
            CREATE TABLE IF NOT EXISTS tutorial_states(user_id TEXT REFERENCES users(id) ON DELETE CASCADE,scope TEXT,version TEXT,body TEXT,PRIMARY KEY(user_id,scope,version));
            ''')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:yield db
        finally:db.close()

    def user_lock(self,user_id):
        with self.lock:return self.user_locks.setdefault(user_id,threading.RLock())

    def create_user(self,username,password,role='student',is_demo=False):
        user_id=secrets.token_hex(12)
        state=initial_state()
        if not is_demo:state['diagnostic_form']='C' if int(user_id[-1],16)%2==0 else 'D'
        with self.connect() as db:
            db.execute('INSERT INTO users VALUES(?,?,?,?,?,?)',(user_id,username,password_hash(password),role,int(is_demo),time.time()))
            db.execute('INSERT INTO states VALUES(?,?)',(user_id,json.dumps(state,ensure_ascii=False)))
        return self.find_user(username)

    def find_user(self,username):
        with self.connect() as db:
            row=db.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
            return dict(row) if row else None

    def list_users(self):
        with self.connect() as db:return [dict(r) for r in db.execute('SELECT * FROM users ORDER BY created')]

    def authenticate(self,username,password):
        user=self.find_user(username)
        if not user:return None
        salt=user['password'].split(':')[0]
        return user if hmac.compare_digest(password_hash(password,salt),user['password']) else None

    def session(self,user_id):
        token=secrets.token_urlsafe(32)
        with self.connect() as db:db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user_id,time.time()+86400))
        return token

    def session_user(self,token):
        with self.connect() as db:
            row=db.execute('SELECT users.* FROM users JOIN sessions ON users.id=sessions.user_id WHERE token_hash=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
            return dict(row) if row else None

    def logout(self,token):
        with self.connect() as db:db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))

    def load(self,user_id):
        with self.connect() as db:
            row=db.execute('SELECT body FROM states WHERE user_id=?',(user_id,)).fetchone()
            if not row:raise ValueError('账号不存在。')
            state=json.loads(row['body']);state.setdefault('work_history',[]);return state

    def operation(self,user_id,key):
        with self.connect() as db:
            row=db.execute('SELECT * FROM operations WHERE user_id=? AND operation_key=?',(user_id,key)).fetchone()
            return dict(row) if row else None

    def save_operation(self,user_id,key,fingerprint,body,status,media_type):
        with self.connect() as db:
            db.execute('INSERT INTO operations VALUES(?,?,?,?,?,?)',(user_id,key,fingerprint,body,status,media_type))

    def save(self,user_id,state):
        state['revision']+=1
        with self.connect() as db:db.execute('UPDATE states SET body=? WHERE user_id=?',(json.dumps(state,ensure_ascii=False,allow_nan=False),user_id))

    def load_project(self,user_id,project_id,factory):
        if project_id=='retail':return self.load(user_id)
        with self.connect() as db:
            row=db.execute('SELECT body FROM project_states WHERE user_id=? AND project_id=?',(user_id,project_id)).fetchone()
            return json.loads(row['body']) if row else factory()

    def save_project(self,user_id,project_id,state):
        if project_id=='retail':return self.save(user_id,state)
        state['revision']=state.get('revision',0)+1
        with self.connect() as db:
            db.execute('INSERT INTO project_states VALUES(?,?,?) ON CONFLICT(user_id,project_id) DO UPDATE SET body=excluded.body',(user_id,project_id,json.dumps(state,ensure_ascii=False,allow_nan=False)))

    def load_learning(self,user_id,project_id):
        from .learning import initial_learning
        with self.connect() as db:
            row=db.execute('SELECT body FROM learning_states WHERE user_id=? AND project_id=?',(user_id,project_id)).fetchone()
            return json.loads(row['body']) if row else initial_learning()

    def save_learning(self,user_id,project_id,state):
        with self.connect() as db:
            db.execute('INSERT INTO learning_states VALUES(?,?,?) ON CONFLICT(user_id,project_id) DO UPDATE SET body=excluded.body',(user_id,project_id,json.dumps(state,ensure_ascii=False,allow_nan=False)))

    def delete_user(self,user_id):
        with self.connect() as db:db.execute('DELETE FROM users WHERE id=?',(user_id,))

    def load_tutorial(self,user_id,scope,version):
        with self.connect() as db:
            row=db.execute('SELECT body FROM tutorial_states WHERE user_id=? AND scope=? AND version=?',(user_id,scope,version)).fetchone()
            return json.loads(row['body']) if row else {'status':'new','step':0}

    def save_tutorial(self,user_id,scope,version,body):
        with self.connect() as db:
            db.execute('INSERT INTO tutorial_states VALUES(?,?,?,?) ON CONFLICT(user_id,scope,version) DO UPDATE SET body=excluded.body',(user_id,scope,version,json.dumps(body,ensure_ascii=False,allow_nan=False)))

    def create_share(self,user_id,body):
        token=secrets.token_urlsafe(24)
        with self.connect() as db:db.execute('INSERT INTO shares VALUES(?,?,?)',(token,user_id,json.dumps(body,ensure_ascii=False)))
        return token

    def get_share(self,token):
        with self.connect() as db:
            row=db.execute('SELECT body FROM shares WHERE token=?',(token,)).fetchone()
            return json.loads(row['body']) if row else None

    def revoke_shares(self,user_id):
        with self.connect() as db:db.execute('DELETE FROM shares WHERE user_id=?',(user_id,))
