"""Unified audience APIs. All ownership and consent decisions are enforced here."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from app.app_config.settings import settings
from app.dependencies.auth import authenticated_principal, _extract_bearer_token
from app.portal import store

router=APIRouter(prefix='/platform')
workers=ThreadPoolExecutor(max_workers=2,thread_name_prefix='report')

class StrictModel(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Credentials(StrictModel):
    username:str=Field(pattern=r'^[A-Za-z0-9_.-]{3,64}$')
    password:str=Field(min_length=10,max_length=128)
class Registration(Credentials):
    display_name:str=Field(min_length=1,max_length=60)
class Actor(BaseModel):
    user_id:str
    role:str

def actor(authorization:Annotated[str|None,Header()]=None,
          x_user_id:Annotated[str|None,Header(alias='X-User-Id')]=None):
    principal=authenticated_principal(authorization)
    if principal is None:raise HTTPException(401,'请先登录')
    if x_user_id and x_user_id!=principal[0]:raise HTTPException(403,'请求身份不匹配')
    return Actor(user_id=principal[0],role=principal[1])

def actor_id(current:Annotated[Actor,Depends(actor)]):return current.user_id
def professional(current:Annotated[Actor,Depends(actor)]):
    if current.role not in {'reader','reviewer','admin'}:raise HTTPException(403,'需要专业工作台权限')
    return current

def guarded(fn,*args):
    try:return fn(*args)
    except LookupError as exc:raise HTTPException(404,str(exc)) from exc
    except PermissionError as exc:raise HTTPException(403,str(exc)) from exc
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc

def owned(current,rid):
    value=store.get_record(current.user_id,rid)
    if not value:raise HTTPException(404,'记录不存在')
    return value

@router.post('/auth/register',status_code=201)
def register(body:Registration,request:Request):
    # Registration can only create public accounts, never a professional or administrator.
    bucket='register:'+str(request.client.host if request.client else 'local')
    with store.db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT count(*) FROM login_attempts WHERE bucket=? AND at>?',(bucket,time.time()-3600)).fetchone()[0]>=10:
            raise HTTPException(429,'注册请求较多，请稍后重试')
        c.execute('INSERT INTO login_attempts VALUES(?,?)',(bucket,time.time()))
    try:identifier=store.register(body.username,body.password,body.display_name)
    except sqlite3.IntegrityError as exc:raise HTTPException(409,'该用户名无法使用') from exc
    return {'user_id':identifier,'role':'public'}

@router.post('/auth/login')
def login(body:Credentials,request:Request):
    bucket='login:'+str(request.client.host if request.client else 'local')
    result=store.login(body.username,body.password,bucket)
    if result and result.get('limited'):raise HTTPException(429,'尝试次数较多，请稍后再试')
    if not result:raise HTTPException(401,'用户名或密码不正确')
    return result

@router.post('/auth/logout')
def logout(current:Annotated[Actor,Depends(actor)],authorization:Annotated[str|None,Header()]=None):
    token=_extract_bearer_token(authorization)
    if token and token.startswith('ps_'):store.logout(token)
    return {'ok':True}

@router.get('/identity')
def identity(current:Annotated[Actor,Depends(actor)]):
    with store.db() as c:
        row=c.execute('SELECT display_name FROM accounts WHERE id=?',(current.user_id,)).fetchone()
    return dict(user_id=current.user_id,role=current.role,
                display_name=row['display_name'] if row else current.user_id,
                workspaces=['personal']+(['professional','knowledge'] if current.role!='public' else []))

@router.get('/professionals')
def directory(current:Annotated[Actor,Depends(actor)]):
    configured={uid for uid,a in settings.api_auth_users.items() if a.role in {'reader','reviewer','admin'}}
    if not settings.api_auth_users and settings.api_auth_token:configured.add(settings.api_local_user_id)
    with store.db() as c:
        configured.update(r['id'] for r in c.execute("SELECT id FROM accounts WHERE role IN ('reader','reviewer','admin')"))
    return {'items':[{'user_id':uid,'display_name':uid} for uid in sorted(configured)]}

@router.get('/records')
def records(current:Annotated[Actor,Depends(actor)]):return {'items':[r for r in store.records(current.user_id) if r['kind']!='clinical_chat']}
class PersonalNote(StrictModel):
    title:str=Field(min_length=1,max_length=100)
    text:str=Field(min_length=1,max_length=12000)
@router.post('/records',status_code=201)
def note(body:PersonalNote,current:Annotated[Actor,Depends(actor)]):
    return store.add_record(current.user_id,'note',body.title,{'text':body.text,'confirmed':True,'origin':'user_statement'})
@router.post('/records/{rid}/archive')
def archive(rid:str,current:Annotated[Actor,Depends(actor)]):
    guarded(store.archive_record,current.user_id,rid);return {'ok':True}

class Assessment(StrictModel):
    scale_type:Literal['PHQ-9','GAD-7']
    answers:list[StrictInt]=Field(min_length=7,max_length=9)
    save:bool=False
@router.post('/assessments')
def assessment(body:Assessment,current:Annotated[Actor,Depends(actor)]):
    from core.public_support import score
    try:result=score(body.scale_type,body.answers)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    if body.save:result['record_id']=store.add_record(current.user_id,'assessment',body.scale_type+' 自评',result)['id']
    return result

class PublicMessage(StrictModel):
    role:Literal['user','assistant']
    content:str=Field(max_length=5000)
class PublicChat(StrictModel):
    query:str=Field(min_length=1,max_length=4000)
    conversation_id:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')
    save:bool=False
    history:list[PublicMessage]=Field(default_factory=list,max_length=12)
@router.post('/chat')
def public_chat(body:PublicChat,current:Annotated[Actor,Depends(actor)]):
    from core.public_support import answer
    history=[m.model_dump() for m in body.history];record=None
    if not body.query.strip():raise HTTPException(422,'请输入内容')
    if body.conversation_id:
        record=owned(current,body.conversation_id)
        if record['kind']!='chat':raise HTTPException(409,'记录类型不是会话')
        if record['payload'].get('status')=='generating':raise HTTPException(409,'该会话仍在生成，请稍后重试')
        history=record['payload'].get('messages',[])
    if body.save and record is None:
        record=store.add_record(current.user_id,'chat',body.query[:40],{'messages':history,'status':'generating','confirmed':False})
    elif body.save and record:
        history=guarded(store.claim_conversation,current.user_id,record['id'])
    rid=record['id'] if record and body.save else None
    def frame(payload):return 'data: '+json.dumps(payload,ensure_ascii=False)+'\n\n'
    async def stream():
        response='';version=None;complete=False
        if rid:
            store.update_record(current.user_id,rid,{'messages':history,'status':'generating','confirmed':False})
        try:
            yield frame({'status':'accepted','record_id':rid})
            async with asyncio.timeout(120):
                async for payload in answer(body.query,history):
                    if 'knowledge_version' in payload:version=payload['knowledge_version']
                    if payload.get('agent') and payload.get('content'):response+=payload['content']
                    yield frame(payload)
            complete=True
            if rid:store.update_record(current.user_id,rid,{'messages':history+[{'role':'user','content':body.query},{'role':'assistant','content':response}],
                                                           'status':'complete','confirmed':False,'knowledge_version':version})
            yield frame({'done':True,'record_id':rid})
        except asyncio.CancelledError:raise
        except Exception:
            yield frame({'error':'public_answer_incomplete','content':'本轮未完成，请稍后重试；已有文字不代表完整回答。'})
        finally:
            if rid and not complete:
                store.update_record(current.user_id,rid,{'messages':history+[{'role':'user','content':body.query},{'role':'assistant','content':response,'incomplete':True}],
                                                       'status':'interrupted','confirmed':False,'knowledge_version':version})
    return StreamingResponse(stream(),media_type='text/event-stream')

class Share(StrictModel):
    recipient:str=Field(min_length=1,max_length=128)
    record_ids:list[str]=Field(min_length=1,max_length=30)
    hours:int=Field(default=24,ge=1,le=720)
@router.post('/grants',status_code=201)
def share(body:Share,current:Annotated[Actor,Depends(actor)]):
    allowed={r['user_id'] for r in directory(current)['items']}
    if body.recipient not in allowed or body.recipient==current.user_id:raise HTTPException(422,'请选择有效的专业接收人')
    return {'id':guarded(store.grant,current.user_id,body.recipient,list(dict.fromkeys(body.record_ids)),body.hours)}
@router.get('/grants')
def grants(current:Annotated[Actor,Depends(actor)]):return {'items':store.grants(current.user_id)}
@router.post('/grants/{gid}/revoke')
def revoke(gid:str,current:Annotated[Actor,Depends(actor)]):
    guarded(store.revoke,current.user_id,gid);return {'ok':True}
@router.get('/inbox')
def inbox(current:Annotated[Actor,Depends(professional)]):return {'items':store.grants(current.user_id,True)}
@router.get('/grants/{gid}')
def grant_detail(gid:str,current:Annotated[Actor,Depends(actor)]):return guarded(store.read_grant,current.user_id,gid)
class CaseName(StrictModel):
    alias:str=Field(min_length=1,max_length=100)
@router.post('/inbox/{gid}/accept')
def accept(gid:str,body:CaseName,current:Annotated[Actor,Depends(professional)]):
    return {'case_id':guarded(store.accept,current.user_id,gid,body.alias)}
@router.get('/cases')
def cases(current:Annotated[Actor,Depends(professional)]):return {'items':store.cases(current.user_id)}
@router.post('/cases',status_code=201)
def create_case(body:CaseName,current:Annotated[Actor,Depends(professional)]):return {'id':store.create_case(current.user_id,body.alias)}
@router.get('/cases/{cid}')
def case_detail(cid:str,current:Annotated[Actor,Depends(professional)]):return guarded(store.case_detail,current.user_id,cid)

class CaseChat(StrictModel):
    query:str=Field(min_length=1,max_length=4000)
    session_id:str=Field(pattern=r'^[A-Za-z0-9_.:-]{1,128}$')
@router.post('/cases/{cid}/chat')
def case_chat(cid:str,body:CaseChat,current:Annotated[Actor,Depends(professional)]):
    guarded(store.case_detail,current.user_id,cid)
    from app.service.chat_service import stream_chat
    namespace='case_'+cid+'_'+hashlib.sha256(body.session_id.encode()).hexdigest()[:20]
    record=store.add_record(current.user_id,'clinical_chat',body.query[:40],{'case_id':cid,'query':body.query,'session_id':body.session_id,
                                                                        'status':'generating','confirmed':False})
    async def stream():
        chunks=[];done=False;version=None;failed=False
        try:
            async for frame in stream_chat(body.query,current.user_id,namespace):
                for line in frame.splitlines():
                    if not line.startswith('data:'):continue
                    try:value=json.loads(line[5:])
                    except ValueError:continue
                    if value.get('agent') and value.get('content') and not value.get('status'):chunks.append(value['content'])
                    if value.get('knowledge_version'):version=value['knowledge_version']
                    if value.get('error') or value.get('failed'):failed=True
                    if value.get('done'):done=not failed
                yield frame
        finally:
            store.update_record(current.user_id,record['id'],{'case_id':cid,'query':body.query,'session_id':body.session_id,
                'answer':''.join(chunks),'knowledge_version':version,'status':'complete' if done else 'interrupted','confirmed':False})
    return StreamingResponse(stream(),media_type='text/event-stream')
class ConfirmedNote(StrictModel):
    body:str=Field(min_length=1,max_length=20000)
    confirmed:Literal[True]
    share_with_owner:bool=False
@router.post('/cases/{cid}/notes',status_code=201)
def clinical_note(cid:str,body:ConfirmedNote,current:Annotated[Actor,Depends(professional)]):
    return {'id':guarded(store.add_note,current.user_id,cid,body.body,body.share_with_owner)}
@router.get('/feedback')
def feedback(current:Annotated[Actor,Depends(actor)]):return {'items':store.feedback(current.user_id)}

def run_report(owner,rid,stage):
    from core.report_support import extract,explain
    record=store.get_record(owner,rid)
    if not record:return
    payload=record['payload']
    try:
        if stage=='extract':
            text,method=extract(store.data_root()/'uploads'/payload['storage_key'],payload['filename'])
            payload.update(status='extracted',extracted_text=text,extraction_method=method,confirmed=False)
        else:
            payload.update(analysis=explain(payload['confirmed_text']),status='analyzed',analysis_source_sha256=hashlib.sha256(payload['confirmed_text'].encode()).hexdigest())
    except Exception:
        payload.update(status='error',error='文字提取失败，请检查文件清晰度或格式后重新上传。' if stage=='extract' else '分析未完成，可稍后重试。',failed_stage=stage)
    if store.get_record(owner,rid):store.update_record(owner,rid,payload)

@router.post('/reports',status_code=202)
async def upload(current:Annotated[Actor,Depends(actor)],file:UploadFile=File(...)):
    filename=Path((file.filename or 'report').replace('\\','/')).name[:150]
    suffix=Path(filename).suffix.casefold()
    try:
        content=await file.read(20*1024*1024+1)
    finally:await file.close()
    if suffix not in {'.pdf','.docx','.png','.jpg','.jpeg'}:raise HTTPException(415,'支持PDF、DOCX、PNG和JPEG')
    if not content or len(content)>20*1024*1024:raise HTTPException(413,'文件为空或超过20MB')
    valid=(suffix=='.pdf' and content.startswith(b'%PDF-')) or (suffix=='.docx' and content.startswith(b'PK')) or (suffix=='.png' and content.startswith(b'\x89PNG\r\n\x1a\n')) or (suffix in {'.jpg','.jpeg'} and content.startswith(b'\xff\xd8\xff'))
    if not valid:raise HTTPException(415,'文件内容与扩展名不一致')
    pending=[r for r in store.records(current.user_id) if r['payload'].get('status') in {'extracting','analyzing'}]
    if len(pending)>=3:raise HTTPException(429,'请等待正在处理的报告完成')
    folder=store.data_root()/'uploads';folder.mkdir(parents=True,exist_ok=True)
    key=uuid4().hex;(folder/key).write_bytes(content)
    record=store.add_record(current.user_id,'report',filename,{'filename':filename,'storage_key':key,'sha256':hashlib.sha256(content).hexdigest(),
                                                           'status':'extracting','confirmed':False,'size_bytes':len(content)})
    workers.submit(run_report,current.user_id,record['id'],'extract')
    return record

@router.get('/records/{rid}')
def get_record(rid:str,current:Annotated[Actor,Depends(actor)]):return owned(current,rid)

class ConfirmText(StrictModel):
    text:str=Field(min_length=10,max_length=60000)
@router.post('/reports/{rid}/confirm')
def confirm_report(rid:str,body:ConfirmText,current:Annotated[Actor,Depends(actor)]):
    record=owned(current,rid);payload=record['payload']
    if record['kind']!='report' or payload.get('status') not in {'extracted','confirmed','analyzed','error'} or not payload.get('extracted_text'):
        raise HTTPException(409,'请先完成文字提取')
    if body.text!=payload.get('confirmed_text'):
        if payload.get('analysis'):payload.setdefault('previous_analyses',[]).append({'text':payload['confirmed_text'],'analysis':payload.pop('analysis')})
        payload.update(confirmed_text=body.text,confirmed=True,status='confirmed')
    store.update_record(current.user_id,rid,payload);return owned(current,rid)

@router.post('/reports/{rid}/analyze',status_code=202)
def analyze_report(rid:str,current:Annotated[Actor,Depends(actor)]):
    with store.db() as c:
        c.execute('BEGIN IMMEDIATE')
        record=store.record_row(c.execute('SELECT * FROM records WHERE id=? AND owner=? AND archived=0',(rid,current.user_id)).fetchone())
        if not record or record['kind']!='report':raise HTTPException(404,'报告不存在')
        payload=record['payload']
        if payload.get('analysis') or payload.get('status')=='analyzing':return record
        if not payload.get('confirmed') or not payload.get('confirmed_text'):raise HTTPException(409,'请先人工确认识别文字')
        payload['status']='analyzing';payload.pop('error',None)
        c.execute('UPDATE records SET payload=? WHERE id=?',(store.pack(payload),rid))
    workers.submit(run_report,current.user_id,rid,'analyze');return owned(current,rid)

@router.get('/reports/{rid}/download')
def download(rid:str,current:Annotated[Actor,Depends(actor)],grant_id:str|None=None):
    record=store.get_record(current.user_id,rid)
    if record is None and grant_id:
        grant=guarded(store.read_grant,current.user_id,grant_id)
        record=next((r for r in grant['records'] if r['id']==rid),None)
    if not record or record['kind']!='report':raise HTTPException(404,'报告不存在')
    key=record['payload']['storage_key']
    if not re.fullmatch('[a-f0-9]{32}',key):raise HTTPException(404,'文件不存在')
    path=store.data_root()/'uploads'/key
    if not path.is_file():raise HTTPException(404,'文件不存在')
    return FileResponse(path,filename=record['payload']['filename'])

@router.get('/knowledge')
def knowledge(current:Annotated[Actor,Depends(actor)]):
    from core.public_support import knowledge_version,sections,POLICY,METHOD
    rows=sections()
    return {'version':knowledge_version(),'policy_version':POLICY,'retrieval_method':METHOD,
            'review_status':'draft_for_internal_testing','sections':len(rows),'documents':len({r['doc_id'] for r in rows}),
            'sources':list({s['id']:s for r in rows for s in r['sources']}.values())}
