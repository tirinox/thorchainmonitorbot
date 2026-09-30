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


async def _post_settings(api, token, settings):
    async def read_json():
        return {'settings': settings}

    resp = await api._set_settings(SimpleNamespace(path_params={'token': token}, json=read_json))
    return json.loads(resp.body)


WALLETS = {'addresses': {'thor1abc': {'chain': 'THOR', 'track_balance': True, 'min': 0, 'bond_prov': True}}}


@pytest.mark.asyncio
async def test_web_save_keeps_the_keys_the_page_does_not_send():
    # the node-op page manages nop:*, gen:alerts and _messenger only; wallets and language live next to them
    manager = _make_manager()
    token = await manager.generate_new_token(CHANNEL)
    await manager.set_settings(CHANNEL, {
        'nop:ip:on': True, 'nop:slash:threshold': 100, 'gen:alerts': False,
        'lang': 'rus', 'personal:balance-track': WALLETS,
    })
    api = _make_api(manager)

    body = await _post_settings(api, token, {'nop:ip:on': False, 'gen:alerts': True, '_messenger': {'platform': 'telegram'}})
    assert body == {'channel': CHANNEL, 'nodes_set': False, 'settings_set': True}

    saved = await manager.get_settings(CHANNEL)
    assert saved['nop:ip:on'] is False and saved['gen:alerts'] is True  # posted keys win
    assert saved['nop:slash:threshold'] == 100  # untouched keys stay
    assert saved['_messenger'] == {'platform': 'telegram'}
    assert saved['lang'] == 'rus'
    assert saved['personal:balance-track'] == WALLETS  # wallets survive the save


@pytest.mark.asyncio
async def test_web_save_for_a_channel_without_settings_creates_them():
    manager = _make_manager()
    token = await manager.generate_new_token(CHANNEL)
    api = _make_api(manager)

    await _post_settings(api, token, {'nop:ip:on': True})
    assert await manager.get_settings(CHANNEL) == {'nop:ip:on': True}


@pytest.mark.asyncio
async def test_update_settings_ignores_garbage_patch():
    manager = _make_manager()
    await manager.set_settings(CHANNEL, {'lang': 'rus'})

    await manager.update_settings(CHANNEL, None)
    await manager.update_settings(CHANNEL, ['not', 'a', 'dict'])
    await manager.update_settings('', {'lang': 'eng'})

    assert await manager.get_settings(CHANNEL) == {'lang': 'rus'}


@pytest.mark.asyncio
async def test_legacy_token_is_revoked():
    manager = _make_manager()
    token = 'cd' * 16
    _seed_legacy_pair(manager, token)

    await manager.revoke_token(CHANNEL)

    assert await manager.token_channel_db.get(token) is None
    assert manager.db.redis.strings == {}
