"""A/B releases must control real retrieval, SSE, history and cache namespaces together."""
import asyncio
import copy
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from langchain_core.messages import HumanMessage,AIMessage,SystemMessage,ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'agent'))
from core.graph.candidate_preview import CandidatePreview
from core.graph.project_workbench import ProjectWorkbench
from core.graph import project_workbench,runtime_version
from core.graph.snapshot_repository import SnapshotRepository
from core.graph.retriever import retrieve,format_result
from core.graph.evidence_report import render_evidence_report
from core.workflow.graph_manager import AgentGraphManager
from agents.drug_review_agent import DrugReviewAgentNode
from app.service import chat_service
from app.infra.cache import SemanticCache

@pytest.fixture(scope='module')
def releases(tmp_path_factory):
    path=tmp_path_factory.mktemp('linked')/'state.sqlite3'
    store=CandidatePreview(ROOT);w=ProjectWorkbench(store,path)
    s=w.publish(0,'test','A')
    a=s['releases'][0]['id']
    detail=w.detail(w.search('失眠')['items'][0]['id'])
    item=detail['records'][0]['audit_item_ids'][0]
    s=w.decide(1,'test',item,'returned','B excludes one scoped record')
    s=w.publish(2,'test','B');b=s['releases'][0]['id']
    return path,store,a,b,detail['records'][0]['id']

@pytest.fixture
def linked(tmp_path,releases,monkeypatch):
    source,store,a,b,removed=releases
    path=tmp_path/'state.sqlite3';path.write_bytes(source.read_bytes())
    w=ProjectWorkbench(store,path)
    monkeypatch.setattr(project_workbench,'workbench',w)
    return w,a,b,removed

def activate(w,uid):return w.activate(w.status()['revision'],'test',uid)

def test_binding_a_b_a_and_scoped_record_difference(linked):
    w,a,b,removed=linked
    activate(w,a);first=runtime_version.resolve_binding()
    ra=retrieve(first.repository,'失眠')
    activate(w,b);second=runtime_version.resolve_binding()
    rb=retrieve(second.repository,'失眠')
    assert removed in {r['id'] for r in ra['records']}
    assert removed not in {r['id'] for r in rb['records']}
    assert first.identity!=second.identity
    # A pinned request remains A after the pointer changes to B.
    with runtime_version.use_binding(first):
        from tools.graph_tool import query_knowledge_graph
        actual=json.loads(query_knowledge_graph.invoke({'query':'失眠'}))
        assert actual['version']==a and removed in {r['id'] for r in actual['records']}
    assert runtime_version.current_binding() is None
    w.rollback(w.status()['revision'],'test')
    assert runtime_version.resolve_binding().identity==first.identity

def test_no_active_uses_baseline_and_invalid_active_never_falls_back(linked):
    w,a,_,_=linked
    assert runtime_version.resolve_binding().version=='kg_v2'
    activate(w,a)
    with sqlite3.connect(w.path) as c:
        s=json.loads(c.execute('SELECT payload FROM state').fetchone()[0]);s['active']='project-missing'
        c.execute('UPDATE state SET payload=?',(json.dumps(s),))
    with pytest.raises(ValueError):runtime_version.resolve_binding()

def test_report_preserves_conditions_sources_and_no_pair_inference(linked):
    w,a,_,_=linked;activate(w,a);repo=runtime_version.resolve_binding().repository
    result=retrieve(repo,'帕罗西汀和舍曲林联用相互作用')
    assert result['pair_query']
    assert all(r['subject_name'] in {'帕罗西汀','舍曲林'} and r['related_name'] in {'帕罗西汀','舍曲林'} for r in result['records'])
    assert result['context_records']
    payload=json.loads(format_result(result));report=render_evidence_report(payload)
    assert a in report and '不构成所问药物对的直接证据' in report
    proof=(result['records']+result['context_records'])[0]['evidence'][0]
    assert proof['sha256'] and proof['locator'] and proof['scope_conditions']
    assert '适用条件与参数' in report and 'https://' in report

def test_snapshot_rejects_unapproved_payload_even_with_recalculated_hash(linked):
    from core.graph.audit import digest
    w,a,_,_=linked;release=copy.deepcopy(w.published_release(a))
    release['payload']['approved_item_ids']=[]
    release['payload_sha256']=digest(release['payload'])
    with pytest.raises(ValueError):SnapshotRepository(release)

def test_version_history_drops_old_summaries_and_preserves_user_statements(linked):
    w,a,b,_=linked;activate(w,a);first=runtime_version.resolve_binding()
    activate(w,b);second=runtime_version.resolve_binding()
    manager=AgentGraphManager.__new__(AgentGraphManager)
    state=dict(knowledge_binding=second.metadata(),history_knowledge_identity=first.identity,
        user_messages=[HumanMessage('既往用药',id='archived')],messages=[HumanMessage('新问题',id='human'),
        SystemMessage('旧知识摘要',id='summary'),AIMessage('旧版建议',id='ai'),ToolMessage('旧工具结果',tool_call_id='tool',id='result')])
    change=asyncio.run(manager._prepare_knowledge_history(state))
    retained=[m for m in change['messages'] if isinstance(m,HumanMessage)]
    assert [m.content for m in retained]==['既往用药','新问题']
    assert change['history_knowledge_identity']==second.identity
    same=dict(state,history_knowledge_identity=second.identity)
    assert 'messages' not in asyncio.run(manager._prepare_knowledge_history(same))

def test_context_is_task_local_and_propagates_to_thread(linked):
    w,a,b,_=linked;activate(w,a);one=runtime_version.resolve_binding();activate(w,b);two=runtime_version.resolve_binding()
    async def exercise():
        async def query(binding):
            with runtime_version.use_binding(binding):
                await asyncio.sleep(0)
                return await asyncio.to_thread(lambda:runtime_version.current_repository().version)
        return await asyncio.gather(query(one),query(two))
    assert asyncio.run(exercise())==[a,b]
    assert runtime_version.current_binding() is None

class FakeVersionCache:
    available=True
    def __init__(self,rows):self.rows=rows
    async def get_cache(self,q,user):
        answer=self.rows.get((q,user))
        return dict(answer=answer,level='EXACT',distance=0,matched_question=q) if answer else None
    async def set_cache(self,q,response,user_id=None):self.rows[(q,user_id)]=response

class FakeCachePool:
    def __init__(self):self.versions={}
    async def for_knowledge(self,identity):return FakeVersionCache(self.versions.setdefault(identity,{}))

def local_graph():
    manager=AgentGraphManager.__new__(AgentGraphManager)
    async def route(state):return {'next_agent':'drug_interaction'}
    manager.orchestrator=SimpleNamespace(route=route)
    manager.drug_review_node=DrugReviewAgentNode.__new__(DrugReviewAgentNode)
    manager.diagnosis_node=manager.treatment_node=None
    # The short test conversations never reach LLM history compression.
    manager._summary_llm=None
    saver=InMemorySaver()
    return manager.build_graph(checkpointer=saver),saver

@pytest.fixture
def local_chat(monkeypatch):
    graph,saver=local_graph();pool=FakeCachePool()
    monkeypatch.setattr(chat_service,'graph',graph)
    monkeypatch.setattr(chat_service,'checkpointer',saver)
    monkeypatch.setattr(chat_service,'semantic_cache',pool)
    monkeypatch.setattr(chat_service,'memory',None)
    return graph,pool

async def turn(query,session):
    return [json.loads(e.removeprefix('data: ').strip()) async for e in chat_service.stream_chat(query,'test_user',session)]

def test_actual_graph_sse_cache_a_b_a_and_multi_turn(linked,local_chat):
    w,a,b,_=linked;graph,pool=local_chat
    async def exercise():
        activate(w,a);first=await turn('失眠相关药物不良反应','a1')
        assert all(e.get('knowledge_version')==a for e in first)
        assert not any(e.get('error') for e in first)
        cached=await turn('失眠相关药物不良反应','a2')
        assert any(e.get('cache_hit') for e in cached)
        activate(w,b);second=await turn('失眠相关药物不良反应','b1')
        assert all(e.get('knowledge_version')==b for e in second)
        assert not any(e.get('cache_hit') or e.get('error') for e in second)
        # Same session switches too; old A outputs do not reach the new B graph.
        changed=await turn('请继续查看失眠相关药物','a1')
        assert not any(e.get('error') for e in changed)
        state=await graph.aget_state(chat_service.session_config('test_user','a1'))
        assert state.values['history_knowledge_identity'].split(':')[1]==b
        assert all(m.additional_kwargs.get('knowledge_binding',{}).get('version')==b for m in state.values['messages'] if isinstance(m,AIMessage))
        assert len(state.values['user_messages'])==2
        w.rollback(w.status()['revision'],'test')
        reverted=await turn('失眠相关药物不良反应','a3')
        assert all(e.get('knowledge_version')==a for e in reverted)
        assert any(e.get('cache_hit') for e in reverted)
        return first,second
    first,second=asyncio.run(exercise())
    assert ''.join(e.get('content','') for e in first if e.get('agent'))!=''.join(e.get('content','') for e in second if e.get('agent'))

def test_activation_during_answer_does_not_change_pinned_tool_version(linked,local_chat,monkeypatch):
    w,a,b,_=linked;graph,_=local_chat;activate(w,a)
    original=graph.astream
    async def switching(*args,**kwargs):
        activate(w,b)
        async for event in original(*args,**kwargs):yield event
    monkeypatch.setattr(graph,'astream',switching)
    result=asyncio.run(turn('失眠相关药物不良反应','inflight'))
    assert all(e.get('knowledge_version')==a for e in result)
    assert any(e.get('agent')=='drug_interaction' and e.get('content') for e in result)
    assert w.status()['active']==b

def test_failed_version_resolution_returns_error_and_no_cache(linked,local_chat,monkeypatch):
    def fail():raise ValueError('private-path')
    monkeypatch.setattr(runtime_version,'resolve_binding',fail)
    events=asyncio.run(turn('请查询失眠相关记录','bad'))
    assert events[0]['error']=='knowledge_version_unavailable' and events[-1]['done']
    assert 'private-path' not in str(events)
    assert local_chat[1].versions=={}

def test_memory_extraction_uses_only_human_and_separate_namespace(monkeypatch):
    saved=[]
    async def extract(user,text,llm):saved.append((user,text))
    async def state(config):return SimpleNamespace(values={'messages':[HumanMessage('用户症状'),AIMessage('旧版生成结论'),SystemMessage('混合摘要')]})
    monkeypatch.setattr(chat_service,'graph',SimpleNamespace(aget_state=state))
    monkeypatch.setattr(chat_service,'memory',SimpleNamespace(extract_from_conversation=extract))
    asyncio.run(chat_service._extract_long_term_memory({},'doctor'))
    assert saved and saved[0][0].startswith('casefacts_v2_') and saved[0][0]!='doctor'
    assert saved[0][1]=='User: 用户症状'

def test_version_cache_collections_are_separate_and_do_not_use_public(monkeypatch):
    ensured=[]
    monkeypatch.setattr(SemanticCache,'_ensure_collection',lambda self:ensured.append(self.collection_name))
    pool=SemanticCache();pool._available=True
    class Client:
        def query(self,**kwargs):
            assert 'scope == "public"' not in kwargs['filter']
            return []
        def search(self,**kwargs):
            assert 'scope == "public"' not in kwargs['filter']
            assert 'scope == "user"' in kwargs['filter']
            return []
    class Embeddings:
        async def aembed_query(self,q):return [1.0]
    pool._client=Client();pool._embeddings=Embeddings()
    async def exercise():
        a=await pool.for_knowledge('A');b=await pool.for_knowledge('B')
        assert a is await pool.for_knowledge('A')
        assert a.collection_name!=b.collection_name!=pool.collection_name
        assert await a.get_cache('test question','owner') is None
    asyncio.run(exercise());assert len(ensured)==2

def test_cache_context_includes_history_and_memory_and_fails_closed(monkeypatch,linked):
    w,a,_,_=linked;activate(w,a);binding=runtime_version.resolve_binding()
    snapshot=SimpleNamespace(values={})
    async def state(config):return snapshot
    monkeypatch.setattr(chat_service,'graph',SimpleNamespace(aget_state=state))
    monkeypatch.setattr(chat_service,'checkpointer',object())
    async def exercise():
        first=await chat_service._cache_owner('user',{},binding,'')
        assert first!=await chat_service._cache_owner('user',{},binding,'new memory')
        snapshot.values={'messages':[HumanMessage('患者信息',id='1')]}
        assert first!=await chat_service._cache_owner('user',{},binding,'')
        async def fail(config):raise ConnectionError()
        chat_service.graph.aget_state=fail
        assert await chat_service._cache_owner('user',{},binding,'')!=await chat_service._cache_owner('user',{},binding,'')
    asyncio.run(exercise())


def test_graph_browser_and_chat_share_release(linked):
    from app.service import knowledge_graph_service as service
    w,a,b,removed=linked;activate(w,a)
    stats=service.stats();assert stats['version']==a
    hit=service.search('失眠',20)['items'][0]
    graph=service.neighbors(hit['id'],40)
    def record_ids(graph):
        return {r['id'] for item in graph['nodes']+graph['edges'] for r in item['properties']['records']}
    assert graph['version']==a and removed in record_ids(graph)
    entity=service.detail(hit['id'])['entity']
    assert removed in {r['id'] for r in entity['properties']['records']}
    assert all(n['label']!='ClinicalEntry' for n in graph['nodes'])
    activate(w,b)
    graph=service.neighbors(hit['id'],40)
    assert graph['version']==b and removed not in record_ids(graph)


def test_browser_preserves_both_endpoints_and_every_scoped_record(linked):
    w,a,_,_=linked;activate(w,a)
    release=w.published_release(a);frozen=copy.deepcopy(release)
    repo=SnapshotRepository(release)
    original=next(d for d in release['payload']['entities'] if d['entity']['name']=='抑郁障碍')
    uid=original['entity']['id'];graph=repo.neighbors([uid],limit=100)
    expected={r[key] for r in original['records'] for key in ('subject_name','related_name') if r.get(key)}
    assert {n['name'] for n in graph['nodes']}==expected
    assert {'伴精神病性症状','难治性抑郁','非典型抗精神病药'}<=expected
    assert len(graph['nodes'])==len({n['id'] for n in graph['nodes']})
    assert all(e['source']!=e['target'] for e in graph['edges'])
    assert len({tuple(sorted((e['source'],e['target']))) for e in graph['edges']})==len(graph['edges'])
    associated={r['id'] for e in graph['edges'] for r in e['properties']['records']}
    standalone={r['id'] for r in original['records'] if not r.get('related_name') or r['related_name']==r['subject_name']}
    assert associated|standalone=={r['id'] for r in original['records']}
    assert {r['id'] for r in repo.detail(uid)['entity']['properties']['records']}=={r['id'] for r in original['records']}
    assert all(e['source_ids'] and e['properties']['records'] for e in graph['edges'])
    assert release==frozen
    for view in ('working','active'):
        preview=w.detail(uid,view)['browser_graph']
        assert {n['name'] for n in preview['nodes']}==expected
        assert len(preview['edges'])==len(graph['edges'])


def test_node_failure_resets_context_and_no_partial_response_cached(linked,local_chat,monkeypatch):
    w,a,_,_=linked;activate(w,a)
    graph,pool=local_chat
    async def fail(*args,**kwargs):
        yield ('custom',dict(chunk='partial answer',agent='test'))
        raise RuntimeError('private-error')
    monkeypatch.setattr(graph,'astream',fail)
    events=asyncio.run(turn('请审查帕罗西汀','failed'))
    assert any(e.get('error')=='inference_failed' for e in events)
    assert events[-1]['failed'] and 'private-error' not in str(events)
    assert not any(pool.versions.values())


def test_version_metadata_tampering_is_rejected(linked):
    w,a,_,_=linked;activate(w,a)
    binding=runtime_version.resolve_binding();metadata=binding.metadata();metadata['version']='kg_v2'
    with pytest.raises(ValueError):runtime_version.binding_from_metadata(metadata)


@pytest.mark.parametrize('command',['仅做药物资料审查：帕罗西汀','请只做药物审查：舍曲林'])
def test_explicit_drug_only_request_cannot_route_to_diagnosis(monkeypatch,command):
    from agents import orchestrator
    monkeypatch.setattr(orchestrator,'get_stream_writer',lambda:lambda event:None)
    node=orchestrator.OrchestratorAgent.__new__(orchestrator.OrchestratorAgent)
    # No llm is attached: a model call would fail the test.
    result=asyncio.run(node.route({'messages':[HumanMessage(command)],'metadata':{}}))
    assert result['next_agent']=='drug_interaction'


@pytest.mark.parametrize('command,expected',[
    ('请简要整理症状与鉴别方向，不要给出个体处方', 'end'),
    ('患者近两周失眠、情绪低落，请分析', 'treatment_recommend'),
])
def test_diagnosis_only_request_controls_following_stages(monkeypatch,command,expected):
    from agents import orchestrator
    monkeypatch.setattr(orchestrator,'get_stream_writer',lambda:lambda event:None)
    node=orchestrator.OrchestratorAgent.__new__(orchestrator.OrchestratorAgent)

    async def decide(messages):
        return SimpleNamespace(content='differential_diagnosis')

    node.llm=SimpleNamespace(ainvoke=decide)
    result=asyncio.run(node.route({
        'messages':[HumanMessage(command)], 'metadata':{'diagnosis_only':True},
    }))
    assert result['next_agent']=='differential_diagnosis'
    assert AgentGraphManager.__new__(AgentGraphManager)._after_diagnosis(result)==expected


@pytest.mark.parametrize('route,expected',[
    ('differential_diagnosis', ['diagnosis', 'treatment']),
    ('drug_interaction', ['drug']),
])
def test_graph_only_enters_drug_review_when_routed_there(monkeypatch,route,expected):
    calls=[]
    binding=runtime_version.KnowledgeBinding('kg_v2','kg_v2','route-test',object())
    monkeypatch.setattr(runtime_version,'resolve_binding',lambda:binding)
    monkeypatch.setattr(runtime_version,'binding_from_metadata',lambda metadata:binding)
    manager=AgentGraphManager.__new__(AgentGraphManager)

    async def choose(state):
        return {'next_agent':route,'metadata':{}}

    def stage(name):
        async def run(state):
            calls.append(name)
            return {'messages':[AIMessage(content=name)]}
        return run

    manager.orchestrator=SimpleNamespace(route=choose)
    manager.diagnosis_node=stage('diagnosis')
    manager.treatment_node=stage('treatment')
    manager.drug_review_node=stage('drug')
    graph=manager.build_graph()
    result=asyncio.run(graph.ainvoke({
        'messages':[HumanMessage('患者最近3周压力大，心慌，入睡困难。')],
        'user_messages':[], 'metadata':{}, 'knowledge_binding':binding.metadata(),
        'user_id':'test', 'session_id':'route', 'memory_context':'',
    }))
    assert calls==expected
    assert result['messages'][-1].content==expected[-1]
