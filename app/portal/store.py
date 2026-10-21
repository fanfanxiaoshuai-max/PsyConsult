"""Local account, record and consent store, independent of the knowledge ledger."""
from contextlib import contextmanager
from datetime import datetime, timezone
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]

def data_root():
    return Path(os.getenv('PSYCONSULT_PLATFORM_DATA', str(ROOT/'data/platform'))).resolve()

@contextmanager
def db():
    root=data_root(); root.mkdir(parents=True, exist_ok=True)
    conn=sqlite3.connect(root/'platform.sqlite3',timeout=15)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
        display_name TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'public');
      CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id), expires REAL NOT NULL);
      CREATE TABLE IF NOT EXISTS login_attempts(bucket TEXT NOT NULL, at REAL NOT NULL);
      CREATE INDEX IF NOT EXISTS idx_login_attempts ON login_attempts(bucket,at);
      CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,owner TEXT NOT NULL,kind TEXT NOT NULL,
        title TEXT NOT NULL,payload TEXT NOT NULL,created TEXT NOT NULL,archived INTEGER NOT NULL DEFAULT 0);
      CREATE INDEX IF NOT EXISTS idx_records_owner ON records(owner,archived,created);
      CREATE TABLE IF NOT EXISTS grants(id TEXT PRIMARY KEY,owner TEXT NOT NULL,recipient TEXT NOT NULL,
        snapshot TEXT NOT NULL,expires REAL NOT NULL,revoked INTEGER NOT NULL DEFAULT 0,case_id TEXT,created TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY,clinician TEXT NOT NULL,subject_owner TEXT,alias TEXT NOT NULL,created TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY,case_id TEXT NOT NULL REFERENCES cases(id),
        author TEXT NOT NULL,body TEXT NOT NULL,shared INTEGER NOT NULL,created TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY,actor TEXT NOT NULL,action TEXT NOT NULL,target TEXT NOT NULL,created TEXT NOT NULL);
    ''')
    try:
        with conn: yield conn
    finally: conn.close()

def now(): return datetime.now(timezone.utc).isoformat()
def pack(value): return json.dumps(value,ensure_ascii=False)
def audit(c,actor,action,target):
    c.execute('INSERT INTO audit VALUES(?,?,?,?,?)',(uuid4().hex,actor,action,target,now()))

def password_hash(password,salt=None):
    salt=salt or secrets.token_bytes(16)
    digest=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1,dklen=32)
    return base64.b64encode(salt).decode()+':'+base64.b64encode(digest).decode()

def register(username,password,display_name):
    identifier='person_'+uuid4().hex
    with db() as c:
        c.execute('INSERT INTO accounts VALUES(?,?,?,?,?)',(identifier,username.casefold(),display_name,password_hash(password),'public'))
        audit(c,identifier,'account_created',identifier)
    return identifier

def login(username,password,bucket):
    username=username.casefold()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        recent=time.time()-300
        c.execute("DELETE FROM login_attempts WHERE at < ? AND bucket LIKE 'login:%'",(recent,))
        if c.execute('SELECT count(*) FROM login_attempts WHERE bucket=? AND at>?',(bucket,recent)).fetchone()[0]>=10:
            return {'limited':True}
        account=c.execute('SELECT * FROM accounts WHERE username=?',(username,)).fetchone()
        valid=False
        # The dummy hash keeps the missing-account path comparable in cost.
        stored=account['password_hash'] if account else password_hash('not-a-real-password',b'0'*16)
        try:
            salt=base64.b64decode(stored.split(':')[0])
            valid=hmac.compare_digest(stored,password_hash(password,salt)) and account is not None
        except ValueError: pass
        if not valid:
            c.execute('INSERT INTO login_attempts VALUES(?,?)',(bucket,time.time()))
            return None
        token='ps_'+secrets.token_urlsafe(32)
        c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),account['id'],time.time()+8*3600))
        c.execute('DELETE FROM login_attempts WHERE bucket=?',(bucket,))
        audit(c,account['id'],'login',account['id'])
        return {'token':token,'user_id':account['id'],'role':account['role'],'display_name':account['display_name']}

def session_principal(token):
    if not token or not token.startswith('ps_'): return None
    with db() as c:
        row=c.execute('SELECT a.id,a.role FROM sessions s JOIN accounts a ON a.id=s.account_id WHERE token_hash=? AND expires>?',
                      (hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        return (row['id'],row['role']) if row else None

def logout(token):
    with db() as c:c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))

def record_row(row):
    if row is None:return None
    result=dict(row); result['payload']=json.loads(result['payload'])
    return result

def add_record(owner,kind,title,payload):
    identifier=uuid4().hex
    with db() as c:
        c.execute('INSERT INTO records(id,owner,kind,title,payload,created) VALUES(?,?,?,?,?,?)',
                  (identifier,owner,kind,title,pack(payload),now()))
        audit(c,owner,'record_created',identifier)
    return get_record(owner,identifier)

def get_record(owner,identifier):
    with db() as c:return record_row(c.execute('SELECT * FROM records WHERE id=? AND owner=? AND archived=0',(identifier,owner)).fetchone())

def records(owner):
    with db() as c:return [record_row(row) for row in c.execute('SELECT * FROM records WHERE owner=? AND archived=0 ORDER BY created DESC LIMIT 500',(owner,))]

def update_record(owner,identifier,payload):
    with db() as c:
        changed=c.execute('UPDATE records SET payload=? WHERE id=? AND owner=? AND archived=0',(pack(payload),identifier,owner)).rowcount
        if not changed:raise LookupError('记录不存在')

def archive_record(owner,identifier):
    with db() as c:
        changed=c.execute('UPDATE records SET archived=1 WHERE id=? AND owner=? AND archived=0',(identifier,owner)).rowcount
        if not changed:raise LookupError('记录不存在')
        audit(c,owner,'record_archived',identifier)

def grant(owner,recipient,ids,hours):
    identifier=uuid4().hex
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        snapshot=[]
        for rid in ids:
            row=record_row(c.execute('SELECT * FROM records WHERE id=? AND owner=? AND archived=0',(rid,owner)).fetchone())
            if not row:raise LookupError('只能分享自己的有效记录')
            if row['kind'] not in {'note','assessment','report','chat'}:raise PermissionError('专业病例资料不能通过个人授权转发')
            if row['payload'].get('status') in {'pending','extracting','analyzing','generating'}:raise ValueError('请等待资料处理完成')
            snapshot.append(row)
        c.execute('INSERT INTO grants VALUES(?,?,?,?,?,0,NULL,?)',
                  (identifier,owner,recipient,pack(snapshot),time.time()+hours*3600,now()))
        audit(c,owner,'grant_created',identifier)
    return identifier

def grants(actor,inbox=False):
    field='recipient' if inbox else 'owner'
    with db() as c:
        rows=c.execute(f'SELECT id,owner,recipient,expires,revoked,case_id,created FROM grants WHERE {field}=? ORDER BY created DESC LIMIT 500',(actor,)).fetchall()
    return [dict(row,active=not row['revoked'] and row['expires']>time.time()) for row in rows]

def read_grant(actor,identifier):
    with db() as c:
        row=c.execute('SELECT * FROM grants WHERE id=? AND (owner=? OR recipient=?)',(identifier,actor,actor)).fetchone()
        if not row:raise LookupError('授权不存在')
        if row['revoked'] or row['expires']<=time.time():raise PermissionError('授权已撤销或到期')
        audit(c,actor,'grant_read',identifier)
        result=dict(row);result['records']=json.loads(result.pop('snapshot'))
        return result

def revoke(owner,identifier):
    with db() as c:
        if not c.execute('UPDATE grants SET revoked=1 WHERE id=? AND owner=?',(identifier,owner)).rowcount:raise LookupError('授权不存在')
        audit(c,owner,'grant_revoked',identifier)

def accept(clinician,identifier,alias):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM grants WHERE id=? AND recipient=?',(identifier,clinician)).fetchone()
        if not row:raise LookupError('授权不存在')
        if row['revoked'] or row['expires']<=time.time():raise PermissionError('授权已撤销或到期')
        if row['case_id']:return row['case_id']
        cid=uuid4().hex
        c.execute('INSERT INTO cases VALUES(?,?,?,?,?)',(cid,clinician,row['owner'],alias,now()))
        c.execute('UPDATE grants SET case_id=? WHERE id=?',(cid,identifier))
        audit(c,clinician,'grant_accepted',identifier)
        return cid

def create_case(clinician,alias):
    cid=uuid4().hex
    with db() as c:
        c.execute('INSERT INTO cases VALUES(?,?,NULL,?,?)',(cid,clinician,alias,now()))
        audit(c,clinician,'case_created',cid)
    return cid

def cases(clinician):
    with db() as c:return [dict(r) for r in c.execute('SELECT * FROM cases WHERE clinician=? ORDER BY created DESC LIMIT 500',(clinician,))]

def case_detail(clinician,cid):
    with db() as c:
        case=c.execute('SELECT * FROM cases WHERE id=? AND clinician=?',(cid,clinician)).fetchone()
        if not case:raise LookupError('病例不存在')
        notes=[dict(r) for r in c.execute('SELECT * FROM notes WHERE case_id=? ORDER BY created',(cid,))]
        ids=[r['id'] for r in c.execute('SELECT id FROM grants WHERE case_id=? AND recipient=? AND revoked=0 AND expires>?',(cid,clinician,time.time()))]
    consultations=[r for r in records(clinician) if r['kind']=='clinical_chat' and r['payload'].get('case_id')==cid]
    return dict(case,notes=notes,grants=[read_grant(clinician,gid) for gid in ids],consultations=consultations)

def add_note(clinician,cid,body,shared):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM cases WHERE id=? AND clinician=?',(cid,clinician)).fetchone()
        if not row:raise LookupError('病例不存在')
        if shared:
            active=c.execute('SELECT id FROM grants WHERE case_id=? AND recipient=? AND owner=? AND revoked=0 AND expires>?',
                             (cid,clinician,row['subject_owner'],time.time())).fetchone()
            if not row['subject_owner'] or not active:raise PermissionError('没有有效授权，不能向个人空间回传')
        nid=uuid4().hex
        c.execute('INSERT INTO notes VALUES(?,?,?,?,?,?)',(nid,cid,clinician,body,int(shared),now()))
        audit(c,clinician,'confirmed_note_shared' if shared else 'confirmed_note_saved',nid)
        return nid

def feedback(owner):
    with db() as c:
        return [dict(r) for r in c.execute('SELECT n.* FROM notes n JOIN cases c ON c.id=n.case_id WHERE c.subject_owner=? AND n.shared=1 ORDER BY n.created DESC LIMIT 500',(owner,))]

def claim_conversation(owner,rid):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        record=record_row(c.execute("SELECT * FROM records WHERE id=? AND owner=? AND kind='chat' AND archived=0",(rid,owner)).fetchone())
        if not record:raise LookupError('会话不存在')
        if record['payload'].get('status')=='generating':raise ValueError('该会话仍在生成，请稍后重试')
        payload=record['payload'];payload['status']='generating'
        c.execute('UPDATE records SET payload=? WHERE id=?',(pack(payload),rid))
        return payload.get('messages',[])

def recover_interrupted():
    """Single-process local deployment: do not leave jobs stuck after a restart."""
    with db() as c:
        for row in c.execute('SELECT id,payload FROM records WHERE archived=0').fetchall():
            payload=json.loads(row['payload']);status=payload.get('status')
            if status not in {'extracting','analyzing','generating'}:continue
            payload.update(status='interrupted' if status=='generating' else 'error',error='服务曾重启，本次处理未完成；请核对后重试。')
            c.execute('UPDATE records SET payload=? WHERE id=?',(pack(payload),row['id']))
