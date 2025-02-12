import os

import pytest

from api.midgard.parser import MidgardParserV2
from lib.constants import NetworkIdents, THOR_DIVIDER, NATIVE_RUNE_SYMBOL
from lib.utils import load_json
from models.asset import is_rune
from models.tx import ThorCoin, ThorMetaSwap

PATH = './sample_data'
DIV = THOR_DIVIDER


def inner_example_tx_gen(name, directory=PATH):
    data = load_json(os.path.join(directory, name))
    p = MidgardParserV2(network_id=NetworkIdents.CHAOSNET_MULTICHAIN)
    return p.parse_tx_response(data)


@pytest.fixture
def example_tx_gen():
    return inner_example_tx_gen


@pytest.mark.parametrize('fn', [
    'v2_add.json',
    'v2_swap.json',
    'v2_refund.json',
    'v2_withdraw.json',
    'affiliate_merge_test.json',
])
def test_parser_v2_smoke(fn, example_tx_gen):
    res = example_tx_gen(name=fn)
    assert res.tx_count > 0
    assert res.total_count > 0


def test_merge_two_coins():
    a = ThorCoin('1', NATIVE_RUNE_SYMBOL)
    b = ThorCoin('2', NATIVE_RUNE_SYMBOL)
    assert ThorCoin.merge_two(a, b).amount == '3'
    assert is_rune(ThorCoin.merge_two(a, b).asset)

    with pytest.raises(AssertionError):
        ThorCoin.merge_two(ThorCoin('1', 'ffs'), ThorCoin('2', 'abc'))

    with pytest.raises(ValueError):
        ThorCoin.merge_two(ThorCoin('gg', 'THOR'), ThorCoin('2', 'THOR'))

    assert ThorCoin.merge_two(ThorCoin('0', 'THOR'), ThorCoin('0', 'THOR')) == ThorCoin('0', 'THOR')


# noinspection PyTypeChecker
def test_merge_two_swap_events():
    a = ThorMetaSwap('10', [ThorCoin('10', NATIVE_RUNE_SYMBOL), ThorCoin('11', NATIVE_RUNE_SYMBOL)], 333, 1200000)
    b = ThorMetaSwap('20', [ThorCoin('44', NATIVE_RUNE_SYMBOL), ThorCoin('45', NATIVE_RUNE_SYMBOL)], 22, 2300000)
    c = ThorMetaSwap.merge_two(a, b)
    assert c.liquidity_fee == 30
    assert c.trade_slip == 355
    assert len(c.network_fees) == 4
    assert c.trade_target == 3500000

    assert ThorMetaSwap.merge_two(a, None) == a
    assert ThorMetaSwap.merge_two(None, a) == a
    assert ThorMetaSwap.merge_two(None, None) is None


@pytest.fixture
def v2_single_tx_gen(example_tx_gen):
    return lambda: example_tx_gen('v2_single.json').txs[0]


def test_synth(example_tx_gen):
    tx = example_tx_gen('synth_swap.json').txs[0]
    assert tx.input_thor_address == 'sthor1nudqnvdfsf03emu3mue7z6gv8ewd6y2sel6p88'
    assert tx.not_rune_asset(in_only=True).asset == 'ETH/USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48'
    assert tx.not_rune_asset(out_only=True).asset == 'LTC/LTC'

    for k, v in tx.get_asset_summary(in_only=True).items():
        assert k == '💊:ETH/USDC-0XA0B8'
        assert v == 0.001

    assert tx.is_synth_involved

    non_synth_tx = example_tx_gen('synth_swap.json').txs[2]
    assert not non_synth_tx.is_synth_involved


def test_thor_coin():
    c1 = ThorCoin('10', 'FOO')
    c2 = ThorCoin('10', 'FOO')
    c3 = ThorCoin('6', 'FOO')
    c4 = ThorCoin('10', 'TEST')
    assert c1 == c2
    assert {c1, c2} == {c1} == {c2}

    assert c1 != c3 != c4 != c2

    assert ThorCoin(**{
        'asset': 'BIRD', 'amount': '1234567'
    }) == ThorCoin('1234567', 'BIRD')
