from types import SimpleNamespace

from comm.localization import twitter_eng as twitter_eng_module
from comm.localization.eng_base import BaseLocalization
from comm.localization.rus import RussianLocalization
from comm.localization.twitter_eng import TwitterEnglishLocalization
from lib.config import Config


def _make_price_event(chain_state=None):
    return SimpleNamespace(
        is_ath=False,
        market_info=SimpleNamespace(pool_rune_price=1.234),
        btc_pool_rune_price=0.00001234,
        chain_state=chain_state,
    )


def _make_twitter_localization() -> TwitterEnglishLocalization:
    return TwitterEnglishLocalization(Config(data={
        'twitter': {
            'max_length': 280,
        },
    }))


def test_english_price_update_keeps_ref_call_with_fewer_than_two_halted_chains():
    loc = BaseLocalization(Config(data={}))

    text = loc.notification_text_price_update(_make_price_event([
        ('BTC', 'halted'),
        ('ETH', 'ok'),
    ]))

    assert 'trading now' in text


def test_english_price_update_hides_ref_call_with_two_halted_chains():
    loc = BaseLocalization(Config(data={}))

    text = loc.notification_text_price_update(_make_price_event([
        ('BTC', 'halted'),
        ('ETH', 'halted'),
    ]))

    assert 'trading now' not in text


def test_russian_price_update_hides_ref_call_with_two_halted_chains():
    loc = RussianLocalization(Config(data={}))

    text = loc.notification_text_price_update(_make_price_event([
        ('BTC', 'halted'),
        ('ETH', 'halted'),
    ]))

    assert 'торговать сейчас' not in text


def test_twitter_price_update_hides_urls_with_two_halted_chains(monkeypatch):
    monkeypatch.setattr(twitter_eng_module, 'TWITTER_POST_URLS_ENABLED', True)
    loc = _make_twitter_localization()

    text = loc.notification_text_price_update(_make_price_event([
        ('BTC', 'halted'),
        ('ETH', 'halted'),
    ]))

    assert 'Start trading now' not in text
    assert 'CoinGecko' not in text
    assert 'http' not in text


def test_twitter_price_update_keeps_urls_with_fewer_than_two_halted_chains(monkeypatch):
    monkeypatch.setattr(twitter_eng_module, 'TWITTER_POST_URLS_ENABLED', True)
    loc = _make_twitter_localization()

    text = loc.notification_text_price_update(_make_price_event([
        ('BTC', 'halted'),
        ('ETH', 'ok'),
    ]))

    assert 'Start trading now' in text
    assert 'CoinGecko' in text
    assert 'http' in text

