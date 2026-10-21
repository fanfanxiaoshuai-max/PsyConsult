"""Live paid API verification using synthetic cases; never prints model credentials."""
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx
from dotenv import dotenv_values, load_dotenv
from pymilvus import MilvusClient

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / 'agent' / '.env')
sys.path.insert(0, str(ROOT / 'agent'))
from core.workflow.checkpointer import create_redis_checkpointer, close_checkpointer
from core.workflow.graph_manager import AgentGraphManager
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage


def collect(client, query, user, session):
    token = dotenv_values(ROOT / 'agent' / '.env').get('API_AUTH_TOKEN')
    headers = {'X-User-Id': user}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    events = []
    start = time.monotonic()
    with client.stream('POST', 'http://127.0.0.1:5000/api/chat', headers=headers,
                       json={'query': query, 'session_id': session}) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith('data: '):
                events.append(json.loads(line[6:]))
    if not events or events[0].get('status') != 'accepted' or not events[-1].get('done'):
        raise RuntimeError('SSE did not complete normally')
    content = ''.join(e.get('content', '') for e in events if 'status' not in e and 'content' in e)
    if not content.strip():
        raise RuntimeError('SSE returned no model content')
    result = {
        'seconds': round(time.monotonic() - start, 2), 'content_chars': len(content),
        'nodes': [e.get('agent') for e in events if e.get('status') == 'agent_node_start'],
        'tools': [e.get('content') for e in events if e.get('status') == 'agent_tool_call'],
        'cache_hit': any(e.get('agent') == 'semantic_cache' for e in events),
        'done': True,
    }
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


async def checkpoint_snapshot(session):
    saver = await create_redis_checkpointer(os.getenv('REDIS_URL', 'redis://localhost:6379'))
    if saver is None:
        raise RuntimeError('Checkpoint unavailable')
    try:
        graph = AgentGraphManager().build_graph(checkpointer=saver)
        return await graph.aget_state({'configurable': {'thread_id': session}})
    finally:
        await close_checkpointer(saver)


async def seed_compression_case(user, session):
    saver = await create_redis_checkpointer(os.getenv('REDIS_URL', 'redis://localhost:6379'))
    if saver is None:
        raise RuntimeError('Checkpoint unavailable')
    try:
        graph = AgentGraphManager().build_graph(checkpointer=saver)
        messages = []
        for index in range(10):
            messages += [HumanMessage(content=f'教学合成病例，随访记录{index+1}：失眠三周，PHQ-9为12分，无真实患者。'),
                         AIMessage(content=f'教学随访记录{index+1}已记录，需结合病程继续评估。')]
        await graph.aupdate_state({'configurable': {'thread_id': session}},
                                  {'messages': messages, 'user_id': user, 'session_id': session,
                                   'memory_context': '', 'next_agent': '', 'metadata': {}})
    finally:
        await close_checkpointer(saver)


def main():
    run_id = uuid.uuid4().hex[:10]
    user, session = f'repro_e2e_{run_id}', f'repro_session_{run_id}'
    report = {'user_id': user, 'session_id': session, 'synthetic_cases_only': True, 'turns': []}
    report_path = ROOT / 'docs' / 'E2E-VERIFICATION.json'
    cases = [
        ('教学虚构病例：成年人，近三周情绪低落、兴趣下降、早醒、疲乏，否认躁狂史。请做简短鉴别诊断并引用检索资料。', 'differential_diagnosis'),
        ('沿用上一轮虚构病例，假定已明确抑郁发作，请简述非药物和分级治疗原则。', 'treatment_recommend'),
        ('仅做教学风险审查：舍曲林与帕罗西汀能否同时使用？请从图谱检索并简要解释。', 'drug_interaction'),
    ]
    try:
        with httpx.Client(trust_env=False, timeout=httpx.Timeout(300, connect=10)) as client:
            deadline = time.monotonic() + 40
            while True:
                try:
                    client.get('http://127.0.0.1:5000/openapi.json').raise_for_status()
                    break
                except httpx.HTTPError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(1)
            for number, (query, expected_node) in enumerate(cases, 1):
                print(f'Checking live turn {number} ({expected_node})', flush=True)
                result = collect(client, query, user, session)
                report['turns'].append(result)
                if expected_node not in result['nodes']:
                    raise RuntimeError(f'Unexpected route for turn {number}')
            for number in (4, 5):
                print(f'Checking cache turn {number}', flush=True)
                result = collect(client, cases[2][0], user, session)
                report['turns'].append(result)
                if not result['cache_hit']:
                    raise RuntimeError('Repeated query did not hit cache')
            snapshot = asyncio.run(checkpoint_snapshot(session))
            report['checkpoint_message_count'] = len(snapshot.values.get('messages', []))
            stored_humans = [m for m in snapshot.values.get('messages', []) if isinstance(m, HumanMessage)]
            if len(stored_humans) != 5:
                raise RuntimeError('Cache-hit turns were not retained in checkpoint')
            report['five_turns_retained'] = True
            milvus = MilvusClient(uri=f"http://{os.getenv('MILVUS_HOST','localhost')}:{os.getenv('MILVUS_PORT','19530')}")
            try:
                deadline = time.monotonic() + 90
                while True:
                    rows = milvus.query(collection_name='long_term_memory', filter=f'user_id == "{user}"', output_fields=['content'], limit=100, consistency_level='Strong')
                    if rows:
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Five-turn background memory extraction did not produce rows')
                    time.sleep(3)
                report['long_term_memory_rows'] = len(rows)
                from core.memory.memory_manager import MemoryManager
                from config import get_settings
                settings = get_settings()

                async def retrieve():
                    memory = MemoryManager(milvus_host=settings.milvus_host, milvus_port=settings.milvus_port,
                                           embedding_api_key=settings.get_embedding_api_key())
                    await memory.initialize()
                    try:
                        return await memory.load_preferences(user, '患者的主诉、病程和用药背景')
                    finally:
                        await memory.close()
                remembered = asyncio.run(retrieve())
                if not remembered:
                    raise RuntimeError('Stored clinical facts could not be retrieved by new memory manager')
                report['cross_session_memory_retrieval'] = True
            finally:
                milvus.close()
            compression_session = f'repro_compression_{run_id}'
            compression_user = f'repro_compression_user_{run_id}'
            asyncio.run(seed_compression_case(compression_user, compression_session))
            print('Checking history compression using 20 seeded synthetic messages', flush=True)
            result = collect(client, '教学审查：舍曲林和帕罗西汀联用的风险是什么？简短回答。', compression_user, compression_session)
            report['compression_turn'] = result
            compressed = asyncio.run(checkpoint_snapshot(compression_session))
            report['history_compression'] = any(isinstance(m, SystemMessage) and '历史会话摘要' in str(m.content)
                                                 for m in compressed.values.get('messages', []))
            if not report['history_compression']:
                raise RuntimeError('History summary did not appear in checkpoint')
        report['status'] = 'passed'
    except Exception as exc:
        report['status'] = 'failed'
        report['failure_type'] = type(exc).__name__
        # Do not persist exception payloads, HTTP authorization headers or credentials.
        raise
    finally:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS: live routes, SSE, cache, checkpoint, long-term memory and history compression', flush=True)


if __name__ == '__main__':
    main()
