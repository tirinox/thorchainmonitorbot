import json
import os

import pytest

from services.jobs.fetch.tx import merge_affiliate_txs, merge_same_txs
from services.lib.constants import NetworkIdents, THOR_DIVIDER, NATIVE_RUNE_SYMBOL
from services.lib.midgard.parser import MidgardParserV2
from services.models.tx import ThorCoin, ThorMetaSwap, ThorTx

PATH = './tx_examples'
DIV = THOR_DIVIDER


def inner_example_tx_gen(name):
    with open(os.path.join(PATH, name), 'r') as f:
        data = json.load(f)
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
    assert ThorCoin.merge_two(a, b).asset == NATIVE_RUNE_SYMBOL

    with pytest.raises(AssertionError):
        ThorCoin.merge_two(ThorCoin('1', 'ffs'), ThorCoin('2', 'abc'))

    with pytest.raises(ValueError):
        ThorCoin.merge_two(ThorCoin('gg', 'THOR'), ThorCoin('2', 'THOR'))

    assert ThorCoin.merge_two(ThorCoin('0', 'THOR'), ThorCoin('0', 'THOR')) == ThorCoin('0', 'THOR')


# noinspection PyTypeChecker
def test_merge_two_swap_events():
    a = ThorMetaSwap('10', [ThorCoin('10', NATIVE_RUNE_SYMBOL), ThorCoin('11', NATIVE_RUNE_SYMBOL)], '333', '1200000')
    b = ThorMetaSwap('20', [ThorCoin('44', NATIVE_RUNE_SYMBOL), ThorCoin('45', NATIVE_RUNE_SYMBOL)], '22', '2300000')
    c = ThorMetaSwap.merge_two(a, b)
    assert c.liquidity_fee == '30'
    assert c.trade_slip == '355'
    assert len(c.network_fees) == 4
    assert c.trade_target == '3500000'

    assert ThorMetaSwap.merge_two(a, None) == a
    assert ThorMetaSwap.merge_two(None, a) == a
    assert ThorMetaSwap.merge_two(None, None) is None


def test_affiliate_merge_simple(example_tx_gen):
    affiliate_tx_examples = example_tx_gen('affiliate_merge_test.json').txs
    t0, t1 = affiliate_tx_examples[:2]
    t0: ThorTx
    t1: ThorTx
    tm = merge_same_txs(t0, t1)
    assert tm.meta_swap.trade_slip == '123'
    assert tm.meta_swap.trade_target == '1312542530351'
    assert tm.meta_swap.liquidity_fee == '16417504333'

    assert len(tm.meta_swap.network_fees) == 4
    assert tm.meta_swap.network_fees[0].asset == NATIVE_RUNE_SYMBOL
    assert tm.meta_swap.network_fees[0].amount == '2000000'

    assert len(tm.in_tx) == 1
    assert len(tm.out_tx) == 1
    assert tm.out_tx == t0.out_tx == t1.out_tx
    assert tm.type == t0.type == t1.type
    assert tm.pools == t0.pools == t1.pools

    assert len(tm.in_tx[0].coins) == len(t0.in_tx[0].coins) == len(t1.in_tx[0].coins)

    assert tm.first_input_tx_hash == t0.first_input_tx_hash == t1.first_input_tx_hash
    assert tm.in_tx[0].coins[0].amount == '10000000000000'  # (!)


def test_affiliate_merge(example_tx_gen):
    affiliate_tx_examples = example_tx_gen('affiliate_merge_test.json').txs

    merged_txs = merge_affiliate_txs(affiliate_tx_examples)
    assert len(merged_txs) > 0
    assert len(merged_txs) < len(affiliate_tx_examples)  # merged
    assert len(merged_txs) == 15


def test_affiliate_add_merge_single(example_tx_gen):
    affiliate_tx_examples_add = example_tx_gen('affiliate_merge_test_add.json').txs
    merged_txs = merge_affiliate_txs(affiliate_tx_examples_add)
    assert len(affiliate_tx_examples_add) == 2
    assert len(merged_txs) == 1
    tx = merged_txs[0]
    assert tx.affiliate_fee == pytest.approx(0.010101, 0.001)


@pytest.mark.parametrize('fn', [
    'affiliate_merge_test_add_2in.json',
    'affiliate_merge_test_add_2in_mix.json'
])
def test_affiliate_add_merge_dual(fn, example_tx_gen):
    affiliate_tx_examples_add = example_tx_gen(fn).txs
    merged_txs = merge_affiliate_txs(affiliate_tx_examples_add)
    assert len(affiliate_tx_examples_add) == 2
    assert len(merged_txs) == 1
    tx = merged_txs[0]
    assert tx.affiliate_fee == pytest.approx(0.0101, 0.001)

    assert tx.in_tx[0].coins[0].amount == '5848107'
    assert tx.in_tx[0].coins[0].asset == 'ETH.ETH'
    assert tx.in_tx[1].coins[0].amount == '3211421250'
    assert tx.in_tx[1].coins[0].asset == NATIVE_RUNE_SYMBOL

@pytest.fixture
def v2_single_tx_gen(example_tx_gen):
    return lambda: example_tx_gen('v2_single.json').txs[0]

def test_merge_same(v2_single_tx_gen):
    tx1 = v2_single_tx_gen()
    tx2 = v2_single_tx_gen()  # same TX, but different objects

    assert tx1.deep_eq(tx2)
    tx1.in_tx[0].coins[0].amount = "123"
    tx2.in_tx[0].coins[0].amount = "234"
    assert not tx1.deep_eq(tx2)
    r = merge_affiliate_txs([tx1, tx2])
    assert len(r) == 1

    tx1 = v2_single_tx_gen()
    tx2 = v2_single_tx_gen()  # same TX, but different objects

    r = merge_affiliate_txs([tx1, tx2])
    assert len(r) == 2
