import asyncio

import langgraph.checkpoint.redis as redis_module
from core.workflow.checkpointer import create_redis_checkpointer, close_checkpointer


class FakeSaver:
    def __init__(self, **kwargs):
        self.options = kwargs
        self.closed = False

    async def asetup(self):
        pass

    async def aset_client_info(self):
        pass

    async def __aexit__(self, *args):
        self.closed = True


def test_default_checkpoint_expires_after_one_day(monkeypatch):
    monkeypatch.setattr(redis_module, 'AsyncRedisSaver', FakeSaver)
    saver = asyncio.run(create_redis_checkpointer('redis://localhost:6379'))
    # The dependency's TTL is minutes: one day is 1440 minutes, not 86400.
    assert saver.options['ttl'] == {'default_ttl': 24 * 60, 'refresh_on_read': True}


def test_checkpoint_context_manager_is_closed(monkeypatch):
    monkeypatch.setattr(redis_module, 'AsyncRedisSaver', FakeSaver)
    saver = asyncio.run(create_redis_checkpointer('redis://localhost:6379'))
    asyncio.run(close_checkpointer(saver))
    assert saver.closed


def test_failed_checkpoint_initialization_closes_connection(monkeypatch):
    instances = []

    class FailingSaver(FakeSaver):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            instances.append(self)

        async def asetup(self):
            raise ConnectionError('offline')

    monkeypatch.setattr(redis_module, 'AsyncRedisSaver', FailingSaver)
    assert asyncio.run(create_redis_checkpointer('redis://localhost:6379')) is None
    assert instances[0].closed
