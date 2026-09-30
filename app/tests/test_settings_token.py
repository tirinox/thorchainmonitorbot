import json
from types import SimpleNamespace

import pytest

from lib.settings_manager import SettingsManager, TokenChannelMap
from tests.fakes import FakeDB
from web_api import AppSettingsAPI

CHANNEL = '123456789'  # a Telegram chat id: public and easy to guess


def _make_manager():
    cfg = SimpleNamespace(as_str=lambda _key: 'https://settings.example')
    return SettingsManager(FakeDB(), cfg)


class FakeNodeWatcher:
    async def all_nodes_for_user(self, _channel_id):
        return ['thor1node']


def _make_api(manager):
    # skip __init__: it needs a config file and Redis
    api = AppSettingsAPI.__new__(AppSettingsAPI)
    api.deps = SimpleNamespace(settings_manager=manager)
    api._node_watcher = FakeNodeWatcher()
    return api


async def _get_settings(api, token):
    resp = await api._get_settings(SimpleNamespace(path_params={'token': token}))
    return json.loads(resp.body)


@pytest.mark.asyncio
async def test_token_resolves_to_its_channel():
    manager = _make_manager()
    token = await manager.generate_new_token(CHANNEL)

    assert TokenChannelMap.TOKEN_RE.fullmatch(token)
    assert await manager.token_channel_db.get(token) == CHANNEL


@pytest.mark.asyncio
async def test_channel_id_is_not_accepted_as_token():
    manager = _make_manager()
    token = await manager.generate_new_token(CHANNEL)
    await manager.set_settings(CHANNEL, {'secret': 'wallets'})
    api = _make_api(manager)

    # the channel id must not reveal the token or the settings
    assert await _get_settings(api, CHANNEL) == {'error': 'channel not found'}

    body = await _get_settings(api, token)
    assert body['channel'] == CHANNEL
    assert body['settings'] == {'secret': 'wallets'}


@pytest.mark.asyncio
async def test_new_token_and_revoke_invalidate_the_old_one():
    manager = _make_manager()
    old_token = await manager.generate_new_token(CHANNEL)
    new_token = await manager.generate_new_token(CHANNEL)

    assert await manager.token_channel_db.get(old_token) is None
    assert await manager.token_channel_db.get(new_token) == CHANNEL

    await manager.revoke_token(CHANNEL)
    assert await manager.token_channel_db.get(new_token) is None
    assert manager.db.redis.strings == {}


def _seed_legacy_pair(manager, token):
    r = manager.db.redis
    r.strings[TokenChannelMap.legacy_key(CHANNEL)] = token
    r.strings[TokenChannelMap.legacy_key(token)] = CHANNEL


@pytest.mark.asyncio
async def test_legacy_token_keeps_working_and_is_migrated():
    manager = _make_manager()
    token = 'ab' * 16
    _seed_legacy_pair(manager, token)

    assert await manager.token_channel_db.get(CHANNEL) is None
    assert await manager.token_channel_db.get(token) == CHANNEL

    assert manager.db.redis.strings == {
        TokenChannelMap.key_by_token(token): CHANNEL,
        TokenChannelMap.key_by_channel(CHANNEL): token,
    }


@pytest.mark.asyncio
async def test_legacy_token_is_revoked():
    manager = _make_manager()
    token = 'cd' * 16
    _seed_legacy_pair(manager, token)

    await manager.revoke_token(CHANNEL)

    assert await manager.token_channel_db.get(token) is None
    assert manager.db.redis.strings == {}
