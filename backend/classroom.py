"""Class-owned records. All reads use explicit ownership in the HTTP layer."""
import json
import secrets
import time


class ClassroomStore:
    def __init__(self,store):
        self.store=store
        with store.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS classes(id TEXT PRIMARY KEY,teacher_id TEXT REFERENCES users(id) ON DELETE CASCADE,name TEXT,project_id TEXT,join_code TEXT UNIQUE,join_enabled INTEGER,revision INTEGER,created REAL);
            CREATE TABLE IF NOT EXISTS class_members(class_id TEXT REFERENCES classes(id) ON DELETE CASCADE,user_id TEXT REFERENCES users(id) ON DELETE CASCADE,created REAL,PRIMARY KEY(class_id,user_id));
            CREATE TABLE IF NOT EXISTS teaching_proposals(id TEXT PRIMARY KEY,class_id TEXT REFERENCES classes(id) ON DELETE CASCADE,user_id TEXT REFERENCES users(id) ON DELETE CASCADE,body TEXT,created REAL);
            CREATE TABLE IF NOT EXISTS teaching_notes(id TEXT PRIMARY KEY,class_id TEXT REFERENCES classes(id) ON DELETE CASCADE,user_id TEXT REFERENCES users(id) ON DELETE CASCADE,body TEXT,created REAL);
            CREATE TABLE IF NOT EXISTS teaching_runs(id TEXT PRIMARY KEY,class_id TEXT REFERENCES classes(id) ON DELETE CASCADE,body TEXT,created REAL);
            CREATE INDEX IF NOT EXISTS class_members_by_user ON class_members(user_id);
            ''')
            # Preserve the original project on historical records before removing
            # class-level binding. The transaction makes this upgrade idempotent.
            for c in db.execute('SELECT id,project_id FROM classes WHERE project_id IS NOT NULL').fetchall():
                for table in ('teaching_proposals','teaching_notes','teaching_runs'):
                    for row in db.execute(f'SELECT id,body FROM {table} WHERE class_id=?',(c['id'],)).fetchall():
                        body=json.loads(row['body']);body.setdefault('project_id',c['project_id'])
                        if table=='teaching_proposals' and body.get('status')=='draft':body['status']='stale'
                        db.execute(f'UPDATE {table} SET body=? WHERE id=?',(json.dumps(body,ensure_ascii=False,allow_nan=False),row['id']))
                db.execute('UPDATE classes SET project_id=NULL,revision=revision+1 WHERE id=?',(c['id'],))

    def get(self,cid):
        with self.store.connect() as db:
            row=db.execute('SELECT c.*,u.username AS teacher_name FROM classes c JOIN users u ON u.id=c.teacher_id WHERE c.id=?',(cid,)).fetchone()
            return dict(row) if row else None

    def user(self,uid):
        with self.store.connect() as db:
            row=db.execute('SELECT id,username,role,is_demo FROM users WHERE id=?',(uid,)).fetchone()
            return dict(row) if row else None

    def owned(self,teacher_id):
        with self.store.connect() as db:
            ids=[r['id'] for r in db.execute('SELECT id FROM classes WHERE teacher_id=? ORDER BY created DESC',(teacher_id,))]
        return [self.get(cid) for cid in ids]

    def members(self,cid):
        with self.store.connect() as db:
            return [dict(r) for r in db.execute('SELECT u.id,u.username,u.is_demo,m.created AS joined FROM class_members m JOIN users u ON u.id=m.user_id WHERE m.class_id=? AND u.role=? ORDER BY m.created',(cid,'student'))]

    def member(self,cid,uid):return next((m for m in self.members(cid) if m['id']==uid),None)

    def create(self,teacher_id,name):
        cid=secrets.token_hex(12)
        with self.store.connect() as db:
            db.execute('INSERT INTO classes VALUES(?,?,?,?,?,?,?,?)',(cid,teacher_id,name,None,secrets.token_hex(5).upper(),1,0,time.time()))
        return self.get(cid)

    def update(self,cid,name,enabled,rotate=False):
        with self.store.connect() as db:
            if rotate:db.execute('UPDATE classes SET name=?,join_enabled=?,join_code=?,revision=revision+1 WHERE id=?',(name,int(enabled),secrets.token_hex(5).upper(),cid))
            else:db.execute('UPDATE classes SET name=?,join_enabled=?,revision=revision+1 WHERE id=?',(name,int(enabled),cid))
        return self.get(cid)

    def by_code(self,code):
        with self.store.connect() as db:
            row=db.execute('SELECT id FROM classes WHERE join_code=? AND join_enabled=1',(code,)).fetchone()
        return self.get(row['id']) if row else None

    def join(self,cid,uid):
        with self.store.connect() as db:
            changed=db.execute('INSERT OR IGNORE INTO class_members VALUES(?,?,?)',(cid,uid,time.time())).rowcount
            if changed:db.execute('UPDATE classes SET revision=revision+1 WHERE id=?',(cid,))

    def leave(self,cid,uid):
        with self.store.connect() as db:
            changed=db.execute('DELETE FROM class_members WHERE class_id=? AND user_id=?',(cid,uid)).rowcount
            if changed:db.execute('UPDATE classes SET revision=revision+1 WHERE id=?',(cid,))

    def joined(self,uid):
        with self.store.connect() as db:
            ids=[r['class_id'] for r in db.execute('SELECT class_id FROM class_members WHERE user_id=? ORDER BY created DESC',(uid,))]
        return [self.get(cid) for cid in ids]

    def rows(self,table,cid,uid=None):
        if table not in ('teaching_proposals','teaching_notes','teaching_runs'):raise ValueError('Unknown teaching table')
        query=f'SELECT id,body,created FROM {table} WHERE class_id=?';args=[cid]
        if uid is not None:query+=' AND user_id=?';args.append(uid)
        with self.store.connect() as db:return [{'id':r['id'],**json.loads(r['body']),'created':r['created']} for r in db.execute(query+' ORDER BY created DESC',args)]

    def put(self,table,cid,body,uid=None,record_id=None):
        if table not in ('teaching_proposals','teaching_notes','teaching_runs'):raise ValueError('Unknown teaching table')
        rid=record_id or secrets.token_hex(12);encoded=json.dumps(body,ensure_ascii=False,allow_nan=False)
        with self.store.connect() as db:
            if record_id:
                query=f'UPDATE {table} SET body=? WHERE id=? AND class_id=?';args=[encoded,rid,cid]
                if uid is not None:query+=' AND user_id=?';args.append(uid)
                if db.execute(query,args).rowcount!=1:raise ValueError('Teaching record no longer exists')
            elif table=='teaching_runs':db.execute('INSERT INTO teaching_runs VALUES(?,?,?,?)',(rid,cid,encoded,time.time()))
            else:db.execute(f'INSERT INTO {table} VALUES(?,?,?,?,?)',(rid,cid,uid,encoded,time.time()))
        return rid

    def project_rows(self,table,cid,pid,uid=None):
        return [r for r in self.rows(table,cid,uid) if r.get('project_id')==pid]

    def student_notes(self,uid,pid):
        notes=[]
        for c in self.joined(uid):
            notes.extend({**r,'class_name':c['name'],'teacher_name':c['teacher_name']} for r in self.project_rows('teaching_notes',c['id'],pid,uid))
        return sorted(notes,key=lambda r:r['created'],reverse=True)[:50]

    def all_runs(self):
        with self.store.connect() as db:return [json.loads(r['body']) for r in db.execute('SELECT body FROM teaching_runs')]

    def commit(self,cid,uid,pid,state,note,memory=None,proposal=None):
        """Student changes, audit note and proposal outcome commit together."""
        encode=lambda obj:json.dumps(obj,ensure_ascii=False,allow_nan=False)
        state['revision']=state.get('revision',0)+1
        with self.store.connect() as db:
            if pid=='retail':db.execute('UPDATE states SET body=? WHERE user_id=?',(encode(state),uid))
            else:db.execute('INSERT INTO project_states VALUES(?,?,?) ON CONFLICT(user_id,project_id) DO UPDATE SET body=excluded.body',(uid,pid,encode(state)))
            if memory is not None:db.execute('INSERT INTO learning_states VALUES(?,?,?) ON CONFLICT(user_id,project_id) DO UPDATE SET body=excluded.body',(uid,pid,encode(memory)))
            db.execute('INSERT INTO teaching_notes VALUES(?,?,?,?,?)',(secrets.token_hex(12),cid,uid,encode({**note,'project_id':pid}),time.time()))
            if proposal:
                rid,body=proposal
                if db.execute('UPDATE teaching_proposals SET body=? WHERE id=? AND class_id=? AND user_id=?',(encode(body),rid,cid,uid)).rowcount!=1:raise ValueError('Proposal no longer exists')
