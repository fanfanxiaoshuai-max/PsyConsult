"""Audience, ownership, consent and report lifecycle regressions using synthetic data."""
import asyncio
import json
import time
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.app_config.settings import settings
from app.portal import router as platform, store
from app.router import chat, transcribe

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('PSYCONSULT_PLATFORM_DATA',str(tmp_path/'platform'))
    monkeypatch.setattr(settings,'api_auth_token','fusion-test-doctor')
    monkeypatch.setattr(settings,'api_auth_users',{})
    monkeypatch.setattr(settings,'api_local_user_id','doctor_001')
    monkeypatch.setattr(settings,'api_local_role','admin')
    app=FastAPI();app.include_router(platform.router,prefix='/api');app.include_router(chat.router,prefix='/api');app.include_router(transcribe.router,prefix='/api')
    with TestClient(app) as c:yield c

def user(client,name='alice'):
    body={'username':name,'password':'synthetic-password-123','display_name':'虚构测试账号'}
    response=client.post('/api/platform/auth/register',json=body)
    assert response.status_code==201,response.text
    session=client.post('/api/platform/auth/login',json={k:body[k] for k in ('username','password')}).json()
    return {'Authorization':'Bearer '+session['token']},session['user_id']

DOCTOR={'Authorization':'Bearer fusion-test-doctor','X-User-Id':'doctor_001'}

def test_public_signup_cannot_escalate_and_clinical_route_is_protected(client):
    bad=client.post('/api/platform/auth/register',json={'username':'bad','password':'synthetic-password-123','display_name':'测试','role':'admin'})
    assert bad.status_code==422
    headers,uid=user(client)
    assert client.get('/api/platform/identity',headers=headers).json()['workspaces']==['personal']
    assert client.get('/api/platform/cases',headers=headers).status_code==403
    assert client.post('/api/chat',headers={**headers,'X-User-Id':uid},json={'query':'仅做药物资料审查','session_id':'session_same'}).status_code==403
    assert client.get('/api/platform/records',headers={**headers,'X-User-Id':'doctor_001'}).status_code==403
    assert client.get('/api/platform/records').status_code==401

def test_logout_invalidates_session_and_no_password_or_token_in_profile(client):
    headers,_=user(client)
    profile=client.get('/api/platform/identity',headers=headers).json()
    assert not {'password','password_hash','token'} & set(profile)
    assert client.post('/api/platform/auth/logout',headers=headers).status_code==200
    assert client.get('/api/platform/identity',headers=headers).status_code==401

def test_personal_record_ownership(client):
    a,_=user(client,'alice');b,_=user(client,'bravo')
    record=client.post('/api/platform/records',headers=a,json={'title':'合成记录','text':'最近睡眠变化，供测试'}).json()
    assert client.get('/api/platform/records/'+record['id'],headers=b).status_code==404
    assert client.post('/api/platform/records/'+record['id']+'/archive',headers=b).status_code==404
    assert client.post('/api/platform/grants',headers=b,json={'recipient':'doctor_001','record_ids':[record['id']],'hours':24}).status_code==404

def test_grant_snapshot_is_explicit_and_revocation_removes_access(client):
    headers,uid=user(client)
    one=store.add_record(uid,'note','选中记录',{'text':'原始用户陈述','confirmed':True})
    two=store.add_record(uid,'note','未选中记录',{'text':'不能自动共享','confirmed':True})
    created=client.post('/api/platform/grants',headers=headers,json={'recipient':'doctor_001','record_ids':[one['id']],'hours':24})
    assert created.status_code==201,created.text
    gid=created.json()['id']
    store.update_record(uid,one['id'],{'text':'授权后的修改','confirmed':True})
    snapshot=client.get('/api/platform/grants/'+gid,headers=DOCTOR).json()
    assert [r['id'] for r in snapshot['records']]==[one['id']]
    assert snapshot['records'][0]['payload']['text']=='原始用户陈述'
    assert two['id'] not in str(snapshot)
    cid=client.post('/api/platform/inbox/'+gid+'/accept',headers=DOCTOR,json={'alias':'虚构病例A'}).json()['case_id']
    assert client.post('/api/platform/cases/'+cid+'/notes',headers=DOCTOR,json={'body':'已核对的测试说明','confirmed':True,'share_with_owner':True}).status_code==201
    assert len(client.get('/api/platform/feedback',headers=headers).json()['items'])==1
    assert client.post('/api/platform/grants/'+gid+'/revoke',headers=headers).status_code==200
    assert client.get('/api/platform/grants/'+gid,headers=DOCTOR).status_code==403
    detail=client.get('/api/platform/cases/'+cid,headers=DOCTOR).json()
    assert detail['grants']==[] and len(detail['notes'])==1
    assert client.post('/api/platform/cases/'+cid+'/notes',headers=DOCTOR,json={'body':'撤销后不能回传','confirmed':True,'share_with_owner':True}).status_code==403

def test_expired_grant_and_unconfirmed_clinical_note_are_rejected(client):
    headers,uid=user(client);rid=store.add_record(uid,'note','合成资料',{'text':'测试'})['id']
    gid=store.grant(uid,'doctor_001',[rid],1)
    with store.db() as c:c.execute('UPDATE grants SET expires=? WHERE id=?',(time.time()-1,gid))
    assert client.get('/api/platform/grants/'+gid,headers=DOCTOR).status_code==403
    cid=client.post('/api/platform/cases',headers=DOCTOR,json={'alias':'合成病例'}).json()['id']
    assert client.post('/api/platform/cases/'+cid+'/notes',headers=DOCTOR,json={'body':'未确认草稿','confirmed':False}).status_code==422

def test_assessment_requires_complete_valid_answers_and_optional_persistence(client):
    headers,_=user(client)
    for answers in ([0]*8,[0]*8+[4],[0]*8+[-1],[0]*8+[True]):
        assert client.post('/api/platform/assessments',headers=headers,json={'scale_type':'PHQ-9','answers':answers}).status_code==422
    result=client.post('/api/platform/assessments',headers=headers,json={'scale_type':'PHQ-9','answers':[0]*8+[1]}).json()
    assert result['total']==1 and result['safety_alert'] and result['screening_only']
    assert client.get('/api/platform/records',headers=headers).json()['items']==[]
    result=client.post('/api/platform/assessments',headers=headers,json={'scale_type':'GAD-7','answers':[1]*7,'save':True}).json()
    assert result['total']==7 and result['record_id']

def test_report_requires_confirmation_and_reuses_analysis_on_archive(client,monkeypatch):
    from core import report_support
    calls=[];jobs=[]
    monkeypatch.setattr(platform.workers,'submit',lambda fn,*args:jobs.append((fn,args)))
    monkeypatch.setattr(report_support,'extract',lambda *args:('合成报告 PHQ-9 总分 11，仅用于测试','pdf_text'))
    monkeypatch.setattr(report_support,'explain',lambda text:(calls.append(text) or '合成辅助解释，不作诊断'))
    headers,_=user(client)
    response=client.post('/api/platform/reports',headers=headers,files={'file':('synthetic.pdf',b'%PDF-1.4 synthetic content','application/pdf')})
    assert response.status_code==202,response.text
    rid=response.json()['id']
    assert client.post(f'/api/platform/reports/{rid}/analyze',headers=headers).status_code==409
    fn,args=jobs.pop(0);fn(*args)
    confirmed=client.post(f'/api/platform/reports/{rid}/confirm',headers=headers,json={'text':'人工核对后的合成报告 PHQ-9 总分 11'})
    assert confirmed.status_code==200
    assert client.post(f'/api/platform/reports/{rid}/analyze',headers=headers).status_code==202
    fn,args=jobs.pop(0);fn(*args)
    assert client.post(f'/api/platform/reports/{rid}/analyze',headers=headers).status_code==202
    assert len(calls)==1 and not jobs
    assert client.get(f'/api/platform/records/{rid}',headers=headers).json()['payload']['analysis']
    assert client.post(f'/api/platform/records/{rid}/archive',headers=headers).status_code==200
    assert len(calls)==1

def test_public_safety_bypasses_model_and_does_not_persist_without_opt_in(client,monkeypatch):
    from core import public_support
    monkeypatch.setattr(public_support,'ChatOpenAI',lambda **kw:pytest.fail('Safety must bypass model'))
    headers,_=user(client)
    response=client.post('/api/platform/chat',headers=headers,json={'query':'我现在打算伤害自己'})
    assert 'safety_support' in response.text and '"done": true' in response.text
    assert client.get('/api/platform/records',headers=headers).json()['items']==[]
    assert not public_support.high_risk('我没有自杀想法，只想了解相关知识')
    assert public_support.high_risk('我没有自杀想法，但是现在准备自杀')

def test_public_unsaved_chat_can_use_transient_history(client,monkeypatch):
    from core import public_support
    observed=[]
    async def fake_answer(query,history):
        observed.extend(history);yield {'agent':'public_support','content':'合成回复'}
    monkeypatch.setattr(public_support,'answer',fake_answer)
    headers,_=user(client)
    response=client.post('/api/platform/chat',headers=headers,json={'query':'然后呢','history':[{'role':'user','content':'先前的合成陈述'}]})
    assert response.status_code==200 and observed[0]['content']=='先前的合成陈述'
    assert not client.get('/api/platform/records',headers=headers).json()['items']

def test_case_chat_scopes_history_by_case_and_preserves_original_stream(client,monkeypatch):
    from app.service import chat_service
    observed=[]
    async def fake(query,user_id,session_id):
        observed.append(session_id)
        yield 'data: {"agent":"diagnosis","content":"合成临床回答"}\n\n'
        yield 'data: {"done":true}\n\n'
    monkeypatch.setattr(chat_service,'stream_chat',fake)
    ids=[store.create_case('doctor_001',name) for name in ('病例A','病例B')]
    for cid in ids:
        response=client.post('/api/platform/cases/'+cid+'/chat',headers=DOCTOR,json={'query':'合成症状描述','session_id':'same_session'})
        assert '"done":true' in response.text
        detail=client.get('/api/platform/cases/'+cid,headers=DOCTOR).json()
        assert len(detail['consultations'])==1
        assert detail['consultations'][0]['payload']['confirmed'] is False
    assert observed[0]!=observed[1]

def test_community_sources_are_scoped_and_versioned():
    from core.public_support import sections,retrieve,knowledge_version
    rows=sections();assert len(rows)==56
    assert all(r['scope'] and r['sources'] for r in rows)
    assert all(s['url'].startswith('https://') for r in rows for s in r['sources'])
    assert retrieve('睡眠问题') and knowledge_version().startswith('community-')

def test_transcription_access_and_validation(client):
    headers,_=user(client)
    assert client.post('/api/transcribe',files={'file':('x.webm',b'','audio/webm')}).status_code==401
    assert client.post('/api/transcribe',headers=headers,files={'file':('x.txt',b'abc','text/plain')}).status_code==415
    assert client.post('/api/transcribe',headers=headers,files={'file':('x.webm',b'','audio/webm')}).status_code==400

def test_existing_professional_token_with_session_prefix_is_still_supported(client,monkeypatch):
    monkeypatch.setattr(settings,'api_auth_token','ps_existing-professional-credential')
    result=client.get('/api/platform/identity',headers={'Authorization':'Bearer ps_existing-professional-credential'})
    assert result.status_code==200 and result.json()['role']=='admin'

def test_saved_conversation_claim_and_restart_recovery_are_explicit(client):
    headers,uid=user(client)
    record=store.add_record(uid,'chat','合成会话',{'messages':[{'role':'user','content':'合成原话'}],'status':'complete'})
    assert store.claim_conversation(uid,record['id'])[0]['content']=='合成原话'
    with pytest.raises(ValueError):store.claim_conversation(uid,record['id'])
    store.recover_interrupted()
    restored=store.get_record(uid,record['id'])
    assert restored['payload']['status']=='interrupted' and restored['payload']['messages'][0]['content']=='合成原话'

def test_structured_vector_evidence_keeps_real_metadata_without_exposing_internal_fields():
    from tools.vector_tool import evidence_row
    from types import SimpleNamespace
    document=SimpleNamespace(page_content='原始内容',metadata={'source':'C:/private/guide.pdf','page':3,'source_url':'https://example.org/guide','internal_secret':'hidden'})
    row=evidence_row(document,.25,1,lambda source,text:text)
    assert row['metadata']['page']==3 and row['metadata']['source_url']=='https://example.org/guide'
    assert 'internal_secret' not in row['metadata'] and row['raw_score']==.25

def test_failed_clinical_terminal_frame_is_not_archived_as_complete(client,monkeypatch):
    from app.service import chat_service
    async def fail(query,user_id,session_id):
        yield 'data: {"error":"inference_failed","content":"合成失败"}\n\n'
        yield 'data: {"done":true,"failed":true}\n\n'
    monkeypatch.setattr(chat_service,'stream_chat',fail)
    cid=store.create_case('doctor_001','虚构失败病例')
    client.post('/api/platform/cases/'+cid+'/chat',headers=DOCTOR,json={'query':'合成问题','session_id':'synthetic_failed'})
    detail=store.case_detail('doctor_001',cid)
    assert detail['consultations'][0]['payload']['status']=='interrupted'
