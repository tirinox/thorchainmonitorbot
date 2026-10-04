from types import SimpleNamespace

import pytest

from comm.localization.eng_base import EnglishLocalization
from comm.localization.rus import RussianLocalization
from comm.localization.twitter_eng import TwitterEnglishLocalization
from lib.config import Config
from notify.alert_presenter import AlertPresenter

CFG = Config(name='./tests/test_config.yaml')


@pytest.mark.parametrize('loc_class, word', [
    (EnglishLocalization, 'unknown'),
    (RussianLocalization, 'неизвестен'),
    (TwitterEnglishLocalization, 'unknown'),
])
def test_no_address_is_an_unknown_user_not_an_empty_link(loc_class, word):
    loc = loc_class(CFG)
    assert loc.link_to_address('', None) == word
    assert loc.link_to_address(None, None) == word
    assert '<a ' not in loc.link_to_address('', None)


def test_an_address_still_gets_its_link_or_caption():
    assert 'runescan.io/address/thor1abcdefgh' in EnglishLocalization(CFG).link_to_address('thor1abcdefgh', None)
    assert TwitterEnglishLocalization(CFG).link_to_address('thor1abcdefgh', None).startswith('[')


def swap_start(from_address):
    return SimpleNamespace(from_address=from_address, tx_id='ABCD', in_asset='XMR.XMR', in_amount_float=2.5,
                           volume_usd=2000.0, out_asset='BTC.BTC')


def test_streaming_swap_start_of_an_unknown_user():
    # the sender of a Monero transaction is not on the chain: THORNode may give an empty address
    text = EnglishLocalization(CFG).notification_text_streaming_swap_started(swap_start(''), None)
    assert 'User: unknown' in text
    assert 'runescan.io/address/"' not in text

    text = RussianLocalization(CFG).notification_text_streaming_swap_started(swap_start(''), None)
    assert 'Пользователь: неизвестен' in text

    text = EnglishLocalization(CFG).notification_text_streaming_swap_started(swap_start('thor1abcdefgh'), None)
    assert 'User: <a href="https://runescan.io/address/thor1abcdefgh"' in text


def test_the_cards_say_it_too():
    gen = AlertPresenter._gen_user_address_for_renderer
    assert gen(None, '', 'unknown') == 'unknown'
    assert gen(None, '') == ''  # nobody asked for a word
    assert gen(None, 'thor1abcdefghijklmnop', 'unknown') == 'thor1a ... mnop'
