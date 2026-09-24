import asyncio
import json

import pytest

from lib.interchan import SimpleRPC
from tests.fakes import FakeDB, FakePubSubRedis


def responses(redis):
    return [(m['__call_id'], m['response']) for ch, m in redis.published if m.get('__type') == 'response']


@pytest.mark.asyncio
async def test_slow_call_does_not_hold_up_the_next_one():
    redis = FakePubSubRedis()
    rpc = SimpleRPC(FakeDB(redis), channel_prefix='test')
    release_slow = asyncio.Event()

    async def handler(payload):
        if payload['name'] == 'slow':
            await release_slow.wait()
        return f"done {payload['name']}"

    rpc._receiver_callback = handler

    # the listener awaits each callback before reading the next message
    await rpc._call_callback('chan', {'__call_id': '1', 'data': {'name': 'slow'}})
    await rpc._call_callback('chan', {'__call_id': '2', 'data': {'name': 'fast'}})
    await asyncio.sleep(0.01)
    assert responses(redis) == [('2', 'done fast')]

    release_slow.set()
    await asyncio.gather(*rpc._call_tasks)
    assert responses(redis) == [('2', 'done fast'), ('1', 'done slow')]


@pytest.mark.asyncio
async def test_failing_call_still_answers_with_the_error():
    redis = FakePubSubRedis()
    rpc = SimpleRPC(FakeDB(redis), channel_prefix='test')

    async def handler(payload):
        raise ValueError('boom')

    rpc._receiver_callback = handler
    await rpc._call_callback('chan', {'__call_id': '7', 'data': {}})
    await asyncio.gather(*rpc._call_tasks)
    [(channel, message)] = redis.published
    assert message['__call_id'] == '7' and message['error'] == 'boom' and message['response'] is None
