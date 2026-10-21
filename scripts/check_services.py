"""Check real database capabilities; no LLM calls, no existing data deletion."""
import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / 'agent' / '.env')
sys.path.insert(0, str(ROOT / 'agent'))


async def redis_check():
    from langgraph.graph import StateGraph, START, END
    from typing import TypedDict
    from core.workflow.checkpointer import create_redis_checkpointer, close_checkpointer
    from redis.asyncio import Redis

    class State(TypedDict):
        value: int

    saver = await create_redis_checkpointer(os.getenv('REDIS_URL', 'redis://localhost:6379'))
    if saver is None:
        raise RuntimeError('Redis checkpoint is disabled')
    try:
        builder = StateGraph(State)
        builder.add_node('increment', lambda state: {'value': state.get('value', 0) + 1})
        builder.add_edge(START, 'increment')
        builder.add_edge('increment', END)
        graph = builder.compile(checkpointer=saver)
        config = {'configurable': {'thread_id': 'repro_probe_' + uuid.uuid4().hex}}
        await graph.ainvoke({'value': 0}, config)
        await close_checkpointer(saver)
        saver = await create_redis_checkpointer(os.getenv('REDIS_URL', 'redis://localhost:6379'))
        if saver is None:
            raise RuntimeError('Checkpoint reconnection failed')
        restored_graph = builder.compile(checkpointer=saver)
        snapshot = await restored_graph.aget_state(config)
        if snapshot.values.get('value') != 1:
            raise RuntimeError('Checkpoint restore failed')
        continued = await restored_graph.ainvoke({}, config)
        if continued.get('value') != 2:
            raise RuntimeError('Checkpoint continuation failed')
        async with Redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379')) as client:
            keys = [key async for key in client.scan_iter(match=f"checkpoint:{config['configurable']['thread_id']}:*")]
            ttls = [await client.ttl(key) for key in keys]
            if not ttls or not all(0 < ttl <= 86400 for ttl in ttls):
                raise RuntimeError(f'Unexpected checkpoint TTL values: {ttls}')
        print(f'PASS: Redis checkpoint write + reconnect + restore + continuation; TTL={min(ttls)}..{max(ttls)} seconds')
        return config
    finally:
        await close_checkpointer(saver)


def milvus_check(infra_only=False):
    from pymilvus import MilvusClient
    client = MilvusClient(uri=f"http://{os.getenv('MILVUS_HOST', 'localhost')}:{os.getenv('MILVUS_PORT', '19530')}", timeout=10)
    try:
        names = client.list_collections()
        print('PASS: Milvus connection')
        for name in ('cloud_product_docs', 'long_term_memory', 'qa_semantic_cache'):
            if name not in names:
                print(f'PENDING: {name} does not exist yet')
            else:
                print(f'{name}: {client.get_collection_stats(name)}')
        if not infra_only and 'cloud_product_docs' not in names:
            raise RuntimeError('RAG collection has not been imported')
    finally:
        client.close()


def neo4j_check():
    from neo4j import GraphDatabase
    with GraphDatabase.driver(os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
                              auth=(os.getenv('NEO4J_USER', 'neo4j'), os.getenv('NEO4J_PASSWORD', 'password123')),
                              connection_timeout=10) as driver:
        driver.verify_connectivity()
        with driver.session() as session:
            count = session.run('MATCH (n) RETURN count(n) AS count').single()['count']
            if not count:
                raise RuntimeError('Neo4j is connected but graph is empty')
            print(f'PASS: Neo4j connected with {count} nodes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--infra-only', action='store_true', help='Allow pending model-dependent Milvus collections')
    args = parser.parse_args()
    failed = []
    for name, check in [('Redis', lambda: asyncio.run(asyncio.wait_for(redis_check(), timeout=40))),
                        ('Milvus', lambda: milvus_check(args.infra_only)), ('Neo4j', neo4j_check)]:
        try:
            check()
        except Exception as exc:
            print(f'FAIL: {name} ({type(exc).__name__})')
            failed.append(name)
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
