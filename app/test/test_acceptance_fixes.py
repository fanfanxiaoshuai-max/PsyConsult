"""Regressions for the system acceptance defects, with synthetic cases only."""
import asyncio
import copy
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import StateGraph, START, END

from app.app_main import app
from app.app_config.settings import APIIdentity, settings
from app.service import chat_service
from core.workflow.state import AgentState
from core.graph import runtime_version
from core.graph.browser_projection import browser_graph, records_with_endpoints
from core.graph.evidence_report import render_chat_review


def test_same_session_different_users_and_cases_are_isolated(monkeypatch):
    async def node(state):
        answer='|'.join(m.content for m in state['messages'] if isinstance(m,HumanMessage))
        get_stream_writer()({'agent':'test','chunk':answer})
        return {'messages':[AIMessage(answer)]}
    builder=StateGraph(AgentState);builder.add_node('test',node);builder.add_edge(START,'test');builder.add_edge('test',END)
    saver=InMemorySaver();graph=builder.compile(checkpointer=saver)
    class NoCache:
        available=False
        async def for_knowledge(self,key):return self
        async def get_cache(self,*args):return None
    monkeypatch.setattr(chat_service,'graph',graph);monkeypatch.setattr(chat_service,'checkpointer',saver)
    monkeypatch.setattr(chat_service,'memory',None);monkeypatch.setattr(chat_service,'semantic_cache',NoCache())
    binding=runtime_version.KnowledgeBinding('test','test','synthetic',None)
    monkeypatch.setattr(runtime_version,'resolve_binding',lambda:binding)
    async def turn(user,session,query):
        rows=[json.loads(e[6:]) async for e in chat_service.stream_chat(query,user,session)]
        return ''.join(r.get('content','') for r in rows if r.get('agent')=='test' and not r.get('status'))
    async def exercise():
        assert await turn('A','same','SYNTHETIC_A')=='SYNTHETIC_A'
        assert await turn('B','same','SYNTHETIC_B')=='SYNTHETIC_B'
        assert await turn('A','other','SYNTHETIC_C')=='SYNTHETIC_C'
        assert await turn('A','same','FOLLOWUP_A')=='SYNTHETIC_A|FOLLOWUP_A'
    asyncio.run(exercise())


def test_long_term_facts_use_the_same_case_namespace_on_read_and_write(monkeypatch):
    facts={}
    async def extract(owner,text,llm):facts[owner]=[text]
    async def load(owner,query):return facts.get(owner,[])
    async def state(config):return SimpleNamespace(values={'user_messages':[HumanMessage('SYNTHETIC_CASE_A')]})
    monkeypatch.setattr(chat_service,'graph',SimpleNamespace(aget_state=state))
    monkeypatch.setattr(chat_service,'memory',SimpleNamespace(long_term=SimpleNamespace(available=True),load_preferences=load,extract_from_conversation=extract))
    async def exercise():
        await chat_service._extract_long_term_memory(chat_service.session_config('doctor','A'),'doctor')
        assert 'SYNTHETIC_CASE_A' in await chat_service._extract_long_term_context('doctor','history','A')
        assert not await chat_service._extract_long_term_context('doctor','history','B')
        assert not await chat_service._extract_long_term_context('other','history','A')
    asyncio.run(exercise())


@pytest.fixture
def accounts(monkeypatch):
    monkeypatch.setattr(settings,'api_auth_users',{
        'doctor':APIIdentity(token='reader-key',role='reader'),
        'reviewer':APIIdentity(token='review-key',role='reviewer'),
        'admin':APIIdentity(token='admin-key',role='admin')})


@pytest.mark.parametrize('token,user,action,expected',[
    ('reader-key','doctor','review',403),('reader-key','doctor','publish',403),
    ('reader-key','admin','publish',403),('review-key','reviewer','publish',403),
    ('reader-key','doctor','activate',403),('reader-key','doctor','rollback',403),
    ('admin-key','admin','publish',200),('review-key','reviewer','review',200),
])
def test_roles_and_authenticated_actor(accounts,monkeypatch,token,user,action,expected):
    from app.router import project_workbench
    calls=[]
    def mutate(*args):calls.append(args);return {'ok':True}
    monkeypatch.setattr(project_workbench,'workbench',SimpleNamespace(publish=mutate,decide=mutate,activate=mutate,rollback=mutate))
    body={'revision':0}
    if action in {'review','publish'}:body['note']='synthetic'
    if action=='review':body.update(item_id='synthetic',status='approved')
    if action=='activate':body['release_id']='project-123456789abc'
    response=TestClient(app).post('/api/knowledge-workbench/'+action,headers={'Authorization':'Bearer '+token,'X-User-Id':user},json=body)
    assert response.status_code==expected,response.text
    assert bool(calls)==(expected==200)
    if calls:assert calls[0][1]==user


def test_identity_is_derived_from_token_and_header_spoof_is_rejected(accounts):
    client=TestClient(app)
    assert client.get('/api/identity',headers={'Authorization':'Bearer reader-key'}).json()=={'user_id':'doctor','role':'reader'}
    assert client.get('/api/knowledge-graph/stats',headers={'Authorization':'Bearer reader-key','X-User-Id':'admin'}).status_code==403


def test_legacy_local_token_cannot_change_identity(monkeypatch):
    monkeypatch.setattr(settings,'api_auth_users',{})
    monkeypatch.setattr(settings,'api_auth_token','local-test')
    monkeypatch.setattr(settings,'api_local_user_id','doctor_001')
    assert TestClient(app).get('/api/knowledge-graph/stats',headers={'Authorization':'Bearer local-test','X-User-Id':'other'}).status_code==403


def test_namesakes_do_not_steal_graph_endpoints_and_legacy_bytes_stay_unchanged():
    entities=[dict(id='disease',name='同名',label='Disease'),dict(id='differential',name='同名',label='DifferentialConsideration'),dict(id='target',name='对象',label='Symptom')]
    record=dict(id='record',subject_name='同名',related_name='对象',evidence=[])
    details=[dict(entity=entities[0],records=[record]),dict(entity=entities[1],records=[]),dict(entity=entities[2],records=[record])]
    original=copy.deepcopy(details)
    restored=records_with_endpoints(details)
    nodes,edges,_=browser_graph(entities,restored,[])
    assert details==original
    assert len(nodes['disease']['properties']['records'])==1
    assert nodes['differential']['properties']['records']==[]
    assert {next(iter(edges.values()))[k] for k in ('source','target')}=={'disease','target'}
    details[1]['records']=[record]
    with pytest.raises(ValueError,match='Ambiguous'):records_with_endpoints(details)


def test_drug_chat_does_not_expand_single_drug_context_into_pair_advice():
    result=dict(version='project-synthetic',pair_query=True,candidates=[dict(name=n,label='Drug') for n in ['甲药','乙药']],records=[],context_records=[{'id':'RAW_RECORD_ID','context':{'unrelated':'x'*15000}}])
    text=render_chat_review(result)
    assert len(text)<400 and '直接相互作用记录' in text and '不能据此判断可安全合用' in text
    assert 'RAW_RECORD_ID' not in text and '{' not in text


def test_concise_drug_record_preserves_scope_without_raw_fields():
    result=dict(version='project-synthetic',candidates=[dict(name='甲药',label='Drug')],records=[dict(id='RAW_ID',title='仅在特定制剂和适应症下适用。',subject_name='甲药',context={'internal':'not-for-chat'},project_review='approved',reasoning_eligible=True,evidence=[dict(scope_conditions='限定成人，不能外推儿童。')])])
    text=render_chat_review(result)
    assert '限定成人' in text and '特定制剂' in text
    assert 'RAW_ID' not in text and 'not-for-chat' not in text


def test_clarification_skips_treatment_and_routing_model(monkeypatch):
    from agents import orchestrator
    monkeypatch.setattr(orchestrator,'get_stream_writer',lambda:lambda e:None)
    monkeypatch.setattr(runtime_version,'current_repository',lambda:SimpleNamespace(entities=lambda:[]))
    node=orchestrator.OrchestratorAgent.__new__(orchestrator.OrchestratorAgent)
    result=asyncio.run(node.route({'messages':[HumanMessage('先复述病程，再给出两个最需要补问的问题。')],'metadata':{}}))
    assert result['next_agent']=='differential_diagnosis' and result['metadata']['diagnosis_only']


def test_routing_model_timeout_falls_back_without_blocking(monkeypatch):
    from agents import orchestrator
    monkeypatch.setattr(orchestrator,'get_stream_writer',lambda:lambda e:None)
    monkeypatch.setattr(runtime_version,'current_repository',lambda:SimpleNamespace(entities=lambda:[]))
    async def never(messages):return SimpleNamespace(content='unused')
    async def timeout(awaitable,timeout):
        awaitable.close()
        assert timeout==20
        raise asyncio.TimeoutError
    monkeypatch.setattr(orchestrator.asyncio,'wait_for',timeout)
    node=orchestrator.OrchestratorAgent.__new__(orchestrator.OrchestratorAgent)
    node.llm=SimpleNamespace(ainvoke=never)
    result=asyncio.run(node.route({'messages':[HumanMessage('请解释目前诊断的治疗思路')],'metadata':{}}))
    assert result['next_agent']=='treatment_recommend'


def test_server_timeout_emits_failed_terminal_frame(monkeypatch):
    async def stalled(*args):
        yield 'data: {"content":"partial"}\n\n'
        await asyncio.sleep(1)
    monkeypatch.setattr(chat_service,'_stream_chat',stalled)
    monkeypatch.setattr(chat_service,'CHAT_TIMEOUT_SECONDS',0.01)
    async def run():return [json.loads(e[6:]) async for e in chat_service.stream_chat('test','doctor','case')]
    events=asyncio.run(run())
    assert events[-2]['error']=='inference_timeout' and events[-1]=={'done':True,'failed':True}


def test_sealed_inventory_validation_has_no_write_side_effect():
    from core.graph.audit import ROOT,freeze
    path=ROOT/'knowledge_sources/v3/inventory.json'
    original=path.stat().st_mtime_ns
    freeze();freeze()
    assert path.stat().st_mtime_ns==original


def test_checked_anxiety_reference_overrides_stale_rag_without_external_service(monkeypatch):
    from tools import vector_tool
    from core.clinical_reference import current_document
    monkeypatch.setattr(vector_tool,'_get_milvus_store',lambda:pytest.fail('Checked local reference must not depend on embeddings'))
    result=vector_tool.query_vector_db.invoke({'query':'心慌 紧张 GAD ICD-11 标准'})
    assert '至少持续数月' in result and 'PDF 第284页' in result
    assert '6B04 社交焦虑障碍' in result
    assert current_document('icd11_anxiety.md','STALE_THRESHOLD')==result.split('】\n',1)[1]
    assert current_document('other.md','other content')=='other content'


def test_symptom_synonyms_do_not_invent_diagnostic_codes_or_scale_answers():
    from tools.synonym_tool import query_synonyms,_load_synonyms
    assert all(row['icd11'] is None and 'phq9_item' not in row and 'gad7_item' not in row for row in _load_synonyms().values())
    result=json.loads(query_synonyms.invoke({'phrase':'心慌'}))
    assert result['term']=='心悸' and result['icd11'] is None
