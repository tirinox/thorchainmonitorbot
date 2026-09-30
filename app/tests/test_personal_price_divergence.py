from types import SimpleNamespace

import pytest

from comm.localization.eng_base import EnglishLocalization
from comm.localization.rus import RussianLocalization
from lib.config import Config
from models.price import RuneMarketInfo
from notify.personal.price_divergence import PersonalPriceDivergenceNotifier, SettingsProcessorPriceDivergence

USER = '42'
MIN_P, MAX_P = 1.0, 5.0


class FakeSettingsManager:
    def __init__(self, settings):
        self.saved = dict(settings)
        self.save_count = 0

    async def get_settings_multi(self, users):
        return {user: dict(self.saved) for user in users}

    async def set_settings(self, _user, settings):
        self.saved = dict(settings)
        self.save_count += 1


class FakeBroadcaster:
    def __init__(self, fail=False):
        self.texts = []
        self.fail = fail

    async def safe_send_message_rate(self, _channel, message, **_kwargs):
        if self.fail:
            raise ConnectionError('telegram is down')
        self.texts.append(message.text)
        return 'good', True


def _make_notifier(loc_class=EnglishLocalization, fail=False):
    loc = loc_class(Config(name='./tests/test_config.yaml'))

    async def all_users_for_node(_node):
        return [USER]

    async def get_from_db(_user, _db):
        return loc

    deps = SimpleNamespace(
        cfg=SimpleNamespace(as_str=lambda _key, default=None: default),
        alert_watcher=SimpleNamespace(all_users_for_node=all_users_for_node),
        settings_manager=FakeSettingsManager({
            SettingsProcessorPriceDivergence.KEY_MIN_PERCENT: MIN_P,
            SettingsProcessorPriceDivergence.KEY_MAX_PERCENT: MAX_P,
        }),
        loc_man=SimpleNamespace(get_from_db=get_from_db),
        broadcaster=FakeBroadcaster(fail),
        db=None,
    )
    return PersonalPriceDivergenceNotifier(deps), deps


def _market(divergence_percent):
    return RuneMarketInfo(pool_rune_price=1.0, cex_price=1.0 + divergence_percent / 100.0)


@pytest.mark.asyncio
@pytest.mark.parametrize('loc_class', [EnglishLocalization, RussianLocalization])
async def test_high_divergence_is_sent_once(loc_class):
    notifier, deps = _make_notifier(loc_class)

    await notifier.on_data(None, _market(8.0))
    await notifier.on_data(None, _market(9.0))  # still above max: no repeat

    assert len(deps.broadcaster.texts) == 1
    assert '🔺' in deps.broadcaster.texts[0]
    assert deps.settings_manager.saved[notifier.LAST_VALUE_KEY] == MAX_P


@pytest.mark.asyncio
async def test_low_divergence_after_high_is_sent():
    notifier, deps = _make_notifier()

    await notifier.on_data(None, _market(8.0))
    await notifier.on_data(None, _market(0.5))

    assert len(deps.broadcaster.texts) == 2
    assert 'Low' in deps.broadcaster.texts[1]
    assert deps.settings_manager.saved[notifier.LAST_VALUE_KEY] == MIN_P


@pytest.mark.asyncio
async def test_threshold_is_kept_when_sending_fails():
    notifier, deps = _make_notifier(fail=True)

    await notifier.on_data(None, _market(8.0))
    assert deps.settings_manager.save_count == 0

    deps.broadcaster.fail = False
    await notifier.on_data(None, _market(8.0))
    assert len(deps.broadcaster.texts) == 1
    assert deps.settings_manager.saved[notifier.LAST_VALUE_KEY] == MAX_P
