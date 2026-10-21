"""Restart only the project's database containers and verify real persisted data."""
import asyncio
import os
import subprocess
import time
from typing import TypedDict

from check_services import ROOT, redis_check
from core.workflow.checkpointer import create_redis_checkpointer, close_checkpointer
from langgraph.graph import StateGraph, START, END
from neo4j import GraphDatabase


class State(TypedDict):
    value: int


def graph_counts():
    with GraphDatabase.driver(os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
                              auth=(os.getenv('NEO4J_USER', 'neo4j'), os.getenv('NEO4J_PASSWORD', 'password123')),
                              connection_timeout=5) as driver:
        with driver.session() as session:
            nodes = session.run('MATCH (n) RETURN count(n) AS count').single()['count']
            edges = session.run('MATCH ()-[r]->() RETURN count(r) AS count').single()['count']
            return nodes, edges


async def restore(config):
    saver = await create_redis_checkpointer(os.getenv('REDIS_URL', 'redis://localhost:6379'))
    if saver is None:
        raise RuntimeError('Redis checkpoint is disabled after restart')
    try:
        builder = StateGraph(State)
        builder.add_node('increment', lambda state: {'value': state.get('value', 0) + 1})
        builder.add_edge(START, 'increment')
        builder.add_edge('increment', END)
        graph = builder.compile(checkpointer=saver)
        snapshot = await graph.aget_state(config)
        if snapshot.values.get('value') != 2:
            raise RuntimeError('Checkpoint was not retained across container restart')
    finally:
        await close_checkpointer(saver)


def main():
    config = asyncio.run(redis_check())
    before = graph_counts()
    subprocess.run(['docker', 'compose', '-f', str(ROOT / 'docker' / 'compose.repro.yml'), 'restart'], check=True)
    # Wait for services to initialize; each connection attempt has bounded timeouts.
    deadline = time.monotonic() + 90
    while True:
        try:
            after = graph_counts()
            if after != before:
                raise RuntimeError(f'Graph counts changed across restart: {before} -> {after}')
            asyncio.run(asyncio.wait_for(restore(config), timeout=20))
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise
            time.sleep(3)
    print(f'PASS: container restart retained checkpoint and graph ({after[0]} nodes, {after[1]} edges)')


if __name__ == '__main__':
    main()
