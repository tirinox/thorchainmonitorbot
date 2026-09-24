import asyncio
from types import SimpleNamespace

import PIL.Image
import pytest

from dashboard.runs import RunManager
from lib.config import Config
from lib.flagship import Flagship
from lib.logs import WithLogger
from lib.run_context import RunMode, current_run, run_context
from notify.alert_preview import AlertPreviewStore
from notify.broadcast import Broadcaster, CapturedMessage
from notify.channel import BoardMessage, ChannelDescriptor
from notify.pub_configure import PublicAlertJobExecutor
from notify.pub_scheduler import PublicScheduler, JobStats
from tests.fakes import FakeDB, FakePubSubRedis

MSG_TYPE = 'public:test_alert'


class FakeLocale:
    def __init__(self, name):
        self.name = name


class FakeLocMan:
    def get_from_lang(self, lang):
        return FakeLocale(lang)


def make_broadcaster(test_channels=(), startup_delay='0'):
    cfg = Config(data={
        'broadcasting': {
            'startup_delay': startup_delay,
            'channels': [
                {'type': 'telegram', 'name': '@public', 'lang': 'eng'},
                {'type': 'twitter', 'name': 'tw', 'lang': 'eng-tw'},
                {'type': 'discord', 'name': '42', 'lang': 'eng'},
            ],
            'test_channels': list(test_channels),
        },
        'personal': {'rate_limit': {'number': 10, 'period': '1m', 'cooldown': '5m'}},
    })
    db = FakeDB(FakePubSubRedis())
    deps = SimpleNamespace(cfg=cfg, db=db, flagship=Flagship(db), loc_man=FakeLocMan())
    broadcaster = Broadcaster(deps)
    sent = []

    async def fake_send(channel_info, message, **kwargs):
        sent.append((channel_info.short_coded, message.text))
        return True

    broadcaster._safe_send_message = fake_send
    return broadcaster, deps, sent


def test_test_channels_are_optional_in_config():
    cfg = Config(data={
        'broadcasting': {'startup_delay': '0', 'channels': []},
        'personal': {'rate_limit': {'number': 10, 'period': '1m', 'cooldown': '5m'}},
    })
    assert Broadcaster(SimpleNamespace(cfg=cfg)).test_channels == []


def text_by_lang(locale):
    return BoardMessage(f'hello in {locale.name}', msg_type=MSG_TYPE)


# ---------- run context ----------

def test_run_context_is_scoped():
    assert current_run().mode == RunMode.NORMAL and current_run().is_real
    with run_context(RunMode.PREVIEW, 'r1'):
        assert current_run().mode == RunMode.PREVIEW and current_run().run_id == 'r1'
        assert not current_run().is_real
    assert current_run().mode == RunMode.NORMAL
    with pytest.raises(ValueError):
        with run_context('bogus'):
            pass


# ---------- broadcaster ----------

@pytest.mark.asyncio
async def test_capture_builds_messages_without_sending():
    broadcaster, deps, sent = make_broadcaster()
    await deps.flagship.set_flag(f'{MSG_TYPE}:broadcast:twitter', False)

    with broadcaster.override_channels(None), broadcaster.capture() as captured:
        await broadcaster.broadcast_to_all(MSG_TYPE, text_by_lang)

    assert sent == []
    assert [(c.channel.short_coded, c.message.text) for c in captured] == [
        ('telegram-@public', 'hello in eng'),
        ('twitter-tw', 'hello in eng-tw'),
        ('discord-42', 'hello in eng'),
    ]
    assert captured[1].blocked_by_flag == f'{MSG_TYPE}:broadcast:twitter'
    assert captured[0].blocked_by_flag is None
    # same language -> the very same generated message
    assert captured[0].message is captured[2].message


@pytest.mark.asyncio
async def test_test_send_goes_only_to_test_channels_despite_flags_and_startup_delay():
    test_channel = {'type': 'telegram', 'name': '@my_test_chat', 'lang': 'rus'}
    broadcaster, deps, sent = make_broadcaster(test_channels=[test_channel], startup_delay='1h')
    await deps.flagship.set_flag(f'{MSG_TYPE}:broadcast:telegram', False)

    # a normal run right after startup is skipped...
    await broadcaster.broadcast_to_all(MSG_TYPE, text_by_lang, channels=['telegram-@public'])
    assert sent == []

    # ...a test send is not, and it only reaches the test channel
    with run_context(RunMode.TEST, 'r1'), broadcaster.override_channels(broadcaster.test_channels):
        await broadcaster.broadcast_to_all(MSG_TYPE, text_by_lang)
    assert sent == [('telegram-@my_test_chat', 'hello in rus')]


# ---------- preview store ----------

@pytest.mark.asyncio
async def test_preview_store_saves_each_image_once():
    db = FakeDB(FakePubSubRedis())
    store = AlertPreviewStore(db)
    image = PIL.Image.new('RGB', (4, 3), 'red')
    photo_msg = BoardMessage.make_photo(image, caption='<b>chart</b>', msg_type=MSG_TYPE)
    jpeg_like = BoardMessage.make_photo(b'\xff\xd8raw-bytes', caption='tw', msg_type=MSG_TYPE)
    channels = [ChannelDescriptor('telegram', '@a', 'eng'), ChannelDescriptor('discord', '1', 'eng'),
                ChannelDescriptor('twitter', 't', 'eng-tw')]
    captured = [CapturedMessage(channels[0], photo_msg), CapturedMessage(channels[1], photo_msg),
                CapturedMessage(channels[2], jpeg_like, 'flag:off')]

    saved = await store.save('run1', captured)
    loaded = await store.load('run1')
    assert loaded == saved
    assert [m['image'] for m in loaded['messages']] == [0, 0, 1]
    assert loaded['messages'][0]['text'] == '<b>chart</b>' and loaded['messages'][0]['message_type'] == 'photo'
    assert loaded['messages'][2]['blocked_by_flag'] == 'flag:off'
    assert (await store.load_image('run1', 0)).startswith(b'\x89PNG')
    assert await store.load_image('run1', 1) == b'\xff\xd8raw-bytes'
    assert await store.load('missing') is None
    assert db.redis.expirations[store._key('run1')] == AlertPreviewStore.TTL_SEC


# ---------- job executor ----------

def make_executor(broadcaster, deps):
    executor = PublicAlertJobExecutor.__new__(PublicAlertJobExecutor)  # skip creating the real fetchers
    WithLogger.__init__(executor)
    executor.deps = deps
    deps.broadcaster = broadcaster

    async def handle_data(data):
        await broadcaster.broadcast_to_all(MSG_TYPE, text_by_lang)

    deps.alert_presenter = SimpleNamespace(handle_data=handle_data)
    return executor


@pytest.mark.asyncio
async def test_executor_preview_stores_messages_and_skips_state():
    broadcaster, deps, sent = make_broadcaster()
    executor = make_executor(broadcaster, deps)
    saved_state = []

    async def save():
        saved_state.append(True)

    with run_context(RunMode.PREVIEW, 'prev1'):
        await executor._send_alert({'some': 'data'}, 'test alert', {'channels': ['telegram-@public']})
        await executor._save_state('thing', save)

    assert sent == [] and saved_state == []
    preview = await AlertPreviewStore(deps.db).load('prev1')
    # a preview shows every public channel, whatever the job's channel filter says
    assert [m['channel']['selector'] for m in preview['messages']] == ['telegram-@public', 'twitter-tw', 'discord-42']

    await executor._save_state('thing', save)  # a normal run saves
    assert saved_state == [True]


@pytest.mark.asyncio
async def test_executor_test_send_needs_test_channels():
    broadcaster, deps, sent = make_broadcaster()
    executor = make_executor(broadcaster, deps)
    with run_context(RunMode.TEST, 't1'):
        with pytest.raises(Exception, match='No test channels'):
            await executor._send_alert({'x': 1}, 'test alert')
    assert sent == []


# ---------- scheduler ----------

@pytest.mark.asyncio
async def test_preview_run_leaves_job_stats_and_history_alone():
    redis = FakePubSubRedis()
    sched = PublicScheduler(cfg=None, db=FakeDB(redis), loop=asyncio.get_running_loop())
    seen_modes = []

    async def my_job(**kwargs):
        seen_modes.append((current_run().mode, current_run().run_id))

    await sched.register_job_type('my_job', my_job)
    result = await sched._on_control_message({'command': 'run_now', 'func': 'my_job', 'run_id': 'p1',
                                              'mode': 'preview'})
    assert result == 'success'
    assert seen_modes == [('preview', 'p1')]
    assert await redis.hgetall(JobStats(sched.db, key='_direct_my_job').key) == {}

    actions = [e['entry']['action'] for e in redis.events('log')]
    assert 'run' not in actions and 'preview_run' in actions

    assert 'unknown run mode' in await sched._on_control_message(
        {'command': 'run_now', 'func': 'my_job', 'mode': 'bogus'})


# ---------- dashboard ----------

@pytest.mark.asyncio
async def test_run_manager_passes_mode_to_the_bot():
    calls = []

    class Sched:
        COMMAND_RUN_NOW = PublicScheduler.COMMAND_RUN_NOW

        async def post_command(self, command, timeout=15.0, **kwargs):
            calls.append(kwargs)
            return 'success'

    manager = RunManager(Sched(), FakeDB(FakePubSubRedis()))
    run = manager.start(job_id='j', mode='preview')
    await asyncio.gather(*manager._tasks)
    assert run.mode == 'preview' and run.status == 'success'
    assert calls[0]['mode'] == 'preview' and calls[0]['run_id'] == run.run_id
    with pytest.raises(ValueError):
        manager.start(job_id='k', mode='bogus')
