import asyncio
import json

import pytest

from lib.interchan import SimpleRPC, PubSubChannel, NoListenerError
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


class ScriptedPubSub:
    """One subscription attempt: fails on subscribe or in listen(), or delivers messages and stays subscribed."""

    def __init__(self, fail_on=None, messages=()):
        self.fail_on = fail_on
        self.messages = messages
        self.closed = False

    async def subscribe(self, _channel):
        if self.fail_on == 'subscribe':
            raise ConnectionError('Redis is down')

    async def listen(self):
        yield {'type': 'subscribe', 'data': 1}
        if self.fail_on == 'listen':
            raise ConnectionError('Connection lost')
        for m in self.messages:
            yield {'type': 'message', 'data': json.dumps(m)}
        await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


class ScriptedRedis:
    def __init__(self, pubsubs):
        self.pubsubs = list(pubsubs)
        self.used = []

    def pubsub(self):
        ps = self.pubsubs.pop(0)
        self.used.append(ps)
        return ps


@pytest.mark.asyncio
async def test_listener_subscribes_again_after_redis_is_lost():
    received = asyncio.Queue()

    async def callback(_channel, data):
        await received.put(data)

    redis = ScriptedRedis([
        ScriptedPubSub(fail_on='listen'),  # redis-py gave up reconnecting
        ScriptedPubSub(fail_on='subscribe'),  # Redis is still down
        ScriptedPubSub(messages=[{'n': 1}]),  # back
    ])
    channel = PubSubChannel(FakeDB(redis), 'test', callback)
    channel.RECONNECT_MIN_DELAY = 0.01
    channel.start()
    try:
        assert await asyncio.wait_for(received.get(), 2) == {'n': 1}
    finally:
        await channel.stop()

    assert len(redis.used) == 3
    assert all(ps.closed for ps in redis.used)


class NoSubscribersRedis(FakePubSubRedis):
    async def publish(self, channel, message):
        await super().publish(channel, message)
        return 0

    async def pubsub_numsub(self, *channels):
        return [(ch, 0) for ch in channels]


@pytest.mark.asyncio
async def test_call_fails_at_once_when_nobody_listens():
    redis = NoSubscribersRedis()
    rpc = SimpleRPC(FakeDB(redis), channel_prefix='test')
    rpc._mode = 'client'  # without starting the response listener

    with pytest.raises(NoListenerError):
        await asyncio.wait_for(rpc({'command': 'run'}, timeout=3600), 1)
    assert rpc._response_collection == {}
    assert await rpc.count_servers() == 0


@pytest.mark.asyncio
async def test_undelivered_response_is_logged(caplog):
    rpc = SimpleRPC(FakeDB(NoSubscribersRedis()), channel_prefix='test')

    async def handler(_payload):
        return 'ok'

    rpc._receiver_callback = handler
    await rpc._call_callback('chan', {'__call_id': '9', 'data': {}})
    await asyncio.gather(*rpc._call_tasks)
    assert 'Nobody received the response to RPC call id 9' in caplog.text
