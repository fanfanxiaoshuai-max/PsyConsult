"""Probe startup fallback against deliberately closed local ports, without stopping services."""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agent'))
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / 'agent' / '.env')
from config import get_settings
from core.workflow.checkpointer import create_redis_checkpointer
from core.workflow.graph_manager import AgentGraphManager
from core.memory.long_term import LongTermMemory
from app.infra.cache import SemanticCache, settings as api_settings


async def main():
    saver = await create_redis_checkpointer('redis://127.0.0.1:1?socket_connect_timeout=1&socket_timeout=1')
    if saver is not None:
        raise RuntimeError('Closed Redis port unexpectedly accepted a connection')
    graph = AgentGraphManager().build_graph(checkpointer=None)
    if 'history_compression' in graph.get_graph().nodes:
        raise RuntimeError('Stateless graph should not contain history compression')
    print('PASS: unavailable Redis produces a stateless graph', flush=True)
    memory = LongTermMemory(host='127.0.0.1', port=1, embedding_api_key=get_settings().get_embedding_api_key())
    await memory.initialize()
    if memory.available or await memory.retrieve_relevant('repro_fallback', 'synthetic query'):
        raise RuntimeError('Unavailable Milvus memory did not fall back')
    await memory.close()
    print('PASS: unavailable Milvus disables long-term memory', flush=True)
    api_settings.milvus_host, api_settings.milvus_port = '127.0.0.1', 1
    cache = SemanticCache()
    await cache.initialize()
    if cache.available or await cache.get_cache('synthetic query', 'repro_fallback') is not None:
        raise RuntimeError('Unavailable Milvus cache did not fall back')
    print('PASS: unavailable Milvus cache returns a miss', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
