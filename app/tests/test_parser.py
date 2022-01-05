import json
import os
from typing import List

import pytest

from services.jobs.fetch.tx import merge_affiliate_txs, merge_same_txs
from services.lib.constants import NetworkIdents, THOR_DIVIDER
from services.lib.midgard.parser import MidgardParserV2
from services.models.tx import ThorCoin, ThorMetaSwap, ThorTx

PATH = './tx_examples'
DIV = THOR_DIVIDER


def inner_example_tx_gen(name):
    with open(os.path.join(PATH, name), 'r') as f:
        return json.load(f)


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
    txs = example_tx_gen(name=fn)
    p = MidgardParserV2(network_id=NetworkIdents.TESTNET_MULTICHAIN)
    res = p.parse_tx_response(txs)
    assert res.tx_count > 0
    assert res.total_count > 0


def test_merge_two_coins():
    a = ThorCoin('1', 'THOR.RUNE')
    b = ThorCoin('2', 'THOR.RUNE')
    assert ThorCoin.merge_two(a, b).amount == '3'
    assert ThorCoin.merge_two(a, b).asset == 'THOR.RUNE'

    with pytest.raises(AssertionError):
        ThorCoin.merge_two(ThorCoin('1', 'ffs'), ThorCoin('2', 'abc'))

    with pytest.raises(ValueError):
        ThorCoin.merge_two(ThorCoin('gg', 'THOR'), ThorCoin('2', 'THOR'))

    assert ThorCoin.merge_two(ThorCoin('0', 'THOR'), ThorCoin('0', 'THOR')) == ThorCoin('0', 'THOR')


def test_merge_two_swap_events():
    a = ThorMetaSwap('10', [ThorCoin('10', 'THOR.RUNE'), ThorCoin('11', 'THOR.RUNE')], '333', '1200000')
    b = ThorMetaSwap('20', [ThorCoin('44', 'THOR.RUNE'), ThorCoin('45', 'THOR.RUNE')], '22', '2300000')
    c = ThorMetaSwap.merge_two(a, b)
    assert c.liquidity_fee == '30'
    assert c.trade_slip == '355'
    assert len(c.network_fees) == 4
    assert c.trade_target == '3500000'

    assert ThorMetaSwap.merge_two(a, None) == a
    assert ThorMetaSwap.merge_two(None, a) == a
    assert ThorMetaSwap.merge_two(None, None) is None


@pytest.fixture
def affiliate_tx_examples(example_tx_gen):
    txs = example_tx_gen(name='affiliate_merge_test.json')
    p = MidgardParserV2(network_id=NetworkIdents.CHAOSNET_MULTICHAIN)
    return p.parse_tx_response(txs).txs


def test_affiliate_merge_simple(affiliate_tx_examples: List[ThorTx]):
    t0, t1 = affiliate_tx_examples[:2]
    t0: ThorTx
    t1: ThorTx
    tm = merge_same_txs([t0, t1])
    assert tm.meta_swap.trade_slip == '123'
    assert tm.meta_swap.trade_target == '1312542530351'
    assert tm.meta_swap.liquidity_fee == '16417504333'

    assert len(tm.meta_swap.network_fees) == 4
    assert tm.meta_swap.network_fees[0].asset == 'THOR.RUNE'
    assert tm.meta_swap.network_fees[0].amount == '2000000'

    assert len(tm.in_tx) == 1
    assert len(tm.out_tx) == 1
    assert tm.out_tx == t0.out_tx == t1.out_tx
    assert tm.type == t0.type == t1.type
    assert tm.pools == t0.pools == t1.pools

    assert len(tm.in_tx[0].coins) == len(t0.in_tx[0].coins) == len(t1.in_tx[0].coins)

    assert tm.first_input_tx_hash == t0.first_input_tx_hash == t1.first_input_tx_hash
    assert tm.in_tx[0].coins[0].amount == '10000000000000'  # (!)


# def test_affiliate_merge_simple_ex(affiliate_tx_examples: List[ThorTx]):
#     t0: ThorTx = affiliate_tx_examples[0]
#     t1: ThorTx = affiliate_tx_examples[2]  # 2! no mistake!
#
#     with pytest.raises(Exception):
#         merge_same_txs([t0, t1])


def test_affiliate_merge(affiliate_tx_examples):
    merged_txs = merge_affiliate_txs(affiliate_tx_examples)
    assert len(merged_txs) > 0
    assert len(merged_txs) < len(affiliate_tx_examples)  # merged
    assert len(merged_txs) == 15
