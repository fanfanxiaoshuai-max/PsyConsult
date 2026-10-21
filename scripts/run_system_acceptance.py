"""Local acceptance probes. Uses synthetic chats; never changes active knowledge releases.

Default: read-only HTTP checks and isolated in-memory session probe.
--live-chat: additionally calls the configured chat model using synthetic cases.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'agent'))
OUT=ROOT/'.tools/acceptance-20261021'
OUT.mkdir(parents=True,exist_ok=True)
results=[]
RESULT_NAME='runtime-probes.json'


def record(name,status,**evidence):
    results.append(dict(name=name,status=status,**evidence))
    (OUT/RESULT_NAME).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(name+': '+status,flush=True)


def http_checks(client,headers):
    stats=client.get('/api/knowledge-graph/stats',headers=headers)
    stats.raise_for_status();stats=stats.json()
    state=client.get('/api/knowledge-workbench/status',headers=headers)
    state.raise_for_status();state=state.json()
    record('active_version_consistency','PASS' if stats['version']==state['active'] else 'FAIL',
        graph_version=stats['version'],active=state['active'],entities=stats['entities'],
        links=stats['relations'],knowledge_records=stats.get('knowledge_records'),counts=state['counts'])
    cases=[('/api/knowledge-graph/stats',{},401),
        ('/api/knowledge-graph/stats',{**headers,'Authorization':'Bearer deliberately-wrong'},401),
        ('/api/knowledge-graph/stats',{**headers,'X-User-Id':'../bad'},400),
        ('/api/knowledge-graph/search?q=%20',headers,422),
        ('/api/knowledge-graph/search?q=x&limit=999',headers,422),
        ('/api/knowledge-graph/entities/acceptance-nonexistent',headers,404)]
    observed=[dict(path=p,expected=expected,actual=client.get(p,headers=h).status_code) for p,h,expected in cases]
    record('http_auth_and_bounds','PASS' if all(x['actual']==x['expected'] for x in observed) else 'FAIL',cases=observed)
    for name in ['抑郁症','双相情感障碍','失眠','帕罗西汀','舍曲林','精神分裂症','6A72']:
        start=time.perf_counter()
        hit=client.get('/api/knowledge-graph/search',params={'q':name},headers=headers)
        hit.raise_for_status();data=hit.json();graph={};detail={}
        if data['items']:
            uid=data['items'][0]['id']
            graph=client.get('/api/knowledge-graph/entities/'+uid+'/neighbors',params={'limit':100},headers=headers).json()
            detail=client.get('/api/knowledge-graph/entities/'+uid,headers=headers).json()
        nodes=graph.get('nodes',[]);edges=graph.get('edges',[])
        valid=bool(data['items']) and bool(detail.get('entity')) and all(e['source'] in {n['id'] for n in nodes} and e['target'] in {n['id'] for n in nodes} for e in edges)
        record('graph_search_'+name,'PASS' if valid else 'FAIL',matches=data['total'],
            nodes=[n['name'] for n in nodes],links=len(edges),
            records=len(detail.get('entity',{}).get('properties',{}).get('records',[])),
            seconds=round(time.perf_counter()-start,3))
    for view in ('working','active'):
        hit=client.get('/api/knowledge-workbench/search',params={'q':'抑郁症','view':view},headers=headers)
        hit.raise_for_status();uid=hit.json()['items'][0]['id']
        response=client.get('/api/knowledge-workbench/entities/'+uid,params={'view':view},headers=headers)
        response.raise_for_status();d=response.json();graph=d['browser_graph']
        record('workbench_browse_'+view,'PASS' if graph['nodes'] and graph['edges'] else 'FAIL',
            records=len(d['records']),entities=len(graph['nodes']),links=len(graph['edges']))
    packet=client.get('/api/knowledge-workbench/export',headers=headers)
    packet.raise_for_status();content=packet.json()
    record('review_export','PASS' if packet.headers.get('content-disposition') and len(content.get('review_rows',[]))==899 else 'FAIL',
        review_rows=len(content.get('review_rows',[])),cache_control=packet.headers.get('cache-control'))
    return stats['version']


def collect(client,headers,name,query,user,session):
    start=time.perf_counter();events=[];first=None;completion=False
    with client.stream('POST','/api/chat',headers={**headers,'X-User-Id':user},json={'query':query,'session_id':session}) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith('data: '):
                if first is None:first=round(time.perf_counter()-start,3)
                event=json.loads(line[6:]);events.append(event)
                if event.get('done'):completion=True
    text=''.join(e.get('content','') for e in events if not e.get('status') and not e.get('error'))
    data=dict(name=name,query=query,user=user,session=session,seconds=round(time.perf_counter()-start,3),
        first_event_seconds=first,done=completion,errors=[e.get('error') for e in events if e.get('error')],
        nodes=[e.get('agent') for e in events if e.get('status')=='agent_node_start'],
        versions=sorted({e['knowledge_version'] for e in events if e.get('knowledge_version')}),
        cache_hit=any(e.get('cache_hit') for e in events),content_chars=len(text),content=text)
    (OUT/(name+'.json')).write_text(json.dumps(dict(data,events=events),ensure_ascii=False,indent=2),encoding='utf-8')
    record(name,'PASS' if completion and text and not data['errors'] else 'FAIL',**{k:v for k,v in data.items() if k not in ('name','content')})
    return data


async def isolated_session_probe(use_redis=False):
    from langchain_core.messages import AIMessage,HumanMessage
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.config import get_stream_writer
    from langgraph.graph import StateGraph,START,END
    from core.workflow.state import AgentState
    from core.graph import runtime_version
    from app.service import chat_service
    async def node(state):
        text=' | '.join(str(m.content) for m in state['messages'] if isinstance(m,HumanMessage))
        get_stream_writer()({'agent':'acceptance_fake','chunk':text})
        return {'messages':[AIMessage(text)]}
    builder=StateGraph(AgentState);builder.add_node('probe',node);builder.add_edge(START,'probe');builder.add_edge('probe',END)
    if use_redis:
        from config import get_settings
        from core.workflow.checkpointer import create_redis_checkpointer
        saver=await create_redis_checkpointer(get_settings().redis_url)
        if saver is None:
            record('cross_user_redis_isolation','UNVERIFIED',reason='Redis checkpointer unavailable')
            return
    else:saver=InMemorySaver()
    graph=builder.compile(checkpointer=saver)
    class Cache:
        available=False
        async def for_knowledge(self,identity):return self
        async def get_cache(self,*args):return None
    chat_service.graph=graph;chat_service.checkpointer=graph.checkpointer;chat_service.memory=None;chat_service.semantic_cache=Cache()
    binding=runtime_version.KnowledgeBinding('acceptance','isolated_probe','synthetic',object())
    runtime_version.resolve_binding=lambda:binding
    marker='SYNTHETIC_PATIENT_A_'+uuid4().hex[:8]
    session='acceptance_shared_'+uuid4().hex
    async def turn(text,user):
        return [json.loads(e.removeprefix('data: ').strip()) async for e in chat_service.stream_chat(text,user,session)]
    await turn(marker,'acceptance_user_A')
    events=await turn('SYNTHETIC_PATIENT_B','acceptance_user_B')
    content=''.join(e.get('content','') for e in events if not e.get('status'))
    record('cross_user_redis_isolation' if use_redis else 'cross_user_same_session_isolation','FAIL' if marker in content else 'PASS',
        fake_model=True,shared_session=True,synthetic_marker_from_user_A_visible_to_B=marker in content,
        checkpointer=type(saver).__name__,note='Exercises actual chat_service configuration; no real user data or LLM call.')
    if use_redis:
        from core.workflow.checkpointer import close_checkpointer
        await close_checkpointer(saver)


def main():
    global OUT
    import httpx
    from app.app_config.settings import settings
    from core.graph.project_workbench import workbench
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--live-chat',action='store_true')
    parser.add_argument('--out',type=Path,default=OUT);args=parser.parse_args()
    OUT=args.out;OUT.mkdir(parents=True,exist_ok=True)
    initial=workbench.status();initial_revision=initial['revision'];initial_active=initial['active']
    headers={'X-User-Id':settings.api_local_user_id}
    if settings.api_auth_token:headers['Authorization']='Bearer '+settings.api_auth_token
    with httpx.Client(base_url='http://127.0.0.1:5000',timeout=httpx.Timeout(210,connect=10),trust_env=False) as client:
        version=http_checks(client,headers)
        user=settings.api_local_user_id;session='acceptance_'+uuid4().hex
        short=collect(client,headers,'short_input','你好',user,session)
        record('short_input_no_inference','PASS' if not short['nodes'] else 'FAIL',nodes=short['nodes'])
        if args.live_chat:
            one=collect(client,headers,'live_symptoms','患者最近3周压力大，心慌，入睡困难。请梳理症状和鉴别方向，不要给出个体处方。',user,session)
            record('symptom_route_no_empty_drug_review','PASS' if 'drug_interaction' not in one['nodes'] and '药物资料审查' not in one['content'] else 'FAIL',nodes=one['nodes'])
            two=collect(client,headers,'live_followup','沿用刚才这位患者的信息，先复述已提供的病程，再给出两个最需要补问的问题。',user,session)
            record('multi_turn_duration_recall','PASS' if ('3周' in two['content'] or '三周' in two['content']) else 'FAIL',manual_confirmation_required=True)
            drug=collect(client,headers,'live_drug_only','仅做药物资料审查：舍曲林与帕罗西汀联用。',user,'acceptance_drug_'+uuid4().hex)
            clinical_nodes=[node for node in drug['nodes'] if node!='orchestrator']
            record('drug_only_route','PASS' if clinical_nodes==['drug_interaction'] else 'FAIL',nodes=drug['nodes'])
            record('live_answer_version_binding','PASS' if all(x['versions']==[version] for x in (one,two,drug)) else 'FAIL',expected_version=version)
    after=workbench.status()
    record('active_release_unchanged','PASS' if after['revision']==initial_revision and after['active']==initial_active else 'FAIL',
        before_revision=initial_revision,after_revision=after['revision'],before_active=initial_active,after_active=after['active'])
    asyncio.run(isolated_session_probe())


if __name__=='__main__':main()
