import os

import pytest

from services.jobs.affiliate_merge import AffiliateTXMerger
from services.lib.constants import NetworkIdents, THOR_DIVIDER, NATIVE_RUNE_SYMBOL, is_rune
from services.lib.midgard.parser import MidgardParserV2
from services.lib.utils import load_json
from services.models.tx import ThorCoin, ThorMetaSwap, ThorTx, ThorSubTx

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
    merger = AffiliateTXMerger()
    tm = merger.merge_same_txs(t0, t1)
    assert tm.meta_swap.trade_slip == '123'
    assert tm.meta_swap.trade_target == '1312542530351'
    assert tm.meta_swap.liquidity_fee == '16417504333'

    assert len(tm.meta_swap.network_fees) == 4
    assert is_rune(tm.meta_swap.network_fees[0].asset)
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

    merged_txs = AffiliateTXMerger().merge_affiliate_txs(affiliate_tx_examples)
    assert len(merged_txs) > 0
    assert len(merged_txs) < len(affiliate_tx_examples)  # merged
    assert len(merged_txs) == 15


def test_affiliate_add_merge_single(example_tx_gen):
    affiliate_tx_examples_add = example_tx_gen('affiliate_merge_test_add.json').txs
    merged_txs = AffiliateTXMerger().merge_affiliate_txs(affiliate_tx_examples_add)
    assert len(affiliate_tx_examples_add) == 2
    assert len(merged_txs) == 1
    tx = merged_txs[0]
    assert tx.affiliate_fee == pytest.approx(0.0119, 0.001)


def test_affiliate_merge_new_add(example_tx_gen):
    affiliate_tx_examples_add = example_tx_gen('add_aff_new.json').txs
    merged_txs = AffiliateTXMerger().merge_affiliate_txs(affiliate_tx_examples_add)
    assert len(merged_txs) == 1

    tx = merged_txs[0]
    assert len(tx.in_tx) == 2

    assert tx.in_tx[0] == ThorSubTx('bc1qtrjyuht0pyggve5lk5k4pheusfpmqh2dzngkwf', [
        ThorCoin(str(77515 + 783), 'BTC.BTC')
    ], 'B84ECCAED2B2D27CE86B7C0D9EF9CE6B18722584D393B0078590172FAD564AC5')

    assert tx.in_tx[1] == ThorSubTx('thor1akth4h8lmawgz933795klfvkvmkej8ldmx6aq9', [
        ThorCoin("990000000", 'THOR.RUNE')
    ], '7E29318D580F7F5E97D93BCB6F0115B0723FE30CE477662608F25CECD45D7B01')



@pytest.mark.parametrize('fn', [
    'affiliate_merge_test_add_2in.json',
    'affiliate_merge_test_add_2in_mix.json'
])
def test_affiliate_add_merge_dual(fn, example_tx_gen):
    affiliate_tx_examples_add = example_tx_gen(fn).txs
    merged_txs = AffiliateTXMerger().merge_affiliate_txs(affiliate_tx_examples_add)
    assert len(affiliate_tx_examples_add) == 2
    assert len(merged_txs) == 1
    tx = merged_txs[0]
    assert tx.affiliate_fee == pytest.approx(0.0101, 0.001)

    assert tx.in_tx[0].coins[0].amount == '5848107'
    assert tx.in_tx[0].coins[0].asset == 'ETH.ETH'
    assert tx.in_tx[1].coins[0].amount == '3211421250'
    assert is_rune(tx.in_tx[1].coins[0].asset)


@pytest.fixture
def v2_single_tx_gen(example_tx_gen):
    return lambda: example_tx_gen('v2_single.json').txs[0]


def test_merge_same_1(v2_single_tx_gen):
    tx1 = v2_single_tx_gen()
    tx2 = v2_single_tx_gen()  # same TX, but different objects

    assert tx1.deep_eq(tx2)
    tx1.in_tx[0].coins[0].amount = "123"
    tx2.in_tx[0].coins[0].amount = "234"
    assert not tx1.deep_eq(tx2)
    r = AffiliateTXMerger().merge_affiliate_txs([tx1, tx2])
    assert len(r) == 1

    tx1 = v2_single_tx_gen()
    tx2 = v2_single_tx_gen()  # same TX, but different objects

    r = AffiliateTXMerger().merge_affiliate_txs([tx1, tx2])
    assert len(r) == 2


def test_synth(example_tx_gen):
    tx = example_tx_gen('synth_swap.json').txs[0]
    assert tx.input_thor_address == 'sthor1nudqnvdfsf03emu3mue7z6gv8ewd6y2sel6p88'
    assert tx.not_rune_asset(in_only=True).asset == 'ETH/USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48'
    assert tx.not_rune_asset(out_only=True).asset == 'LTC/LTC'

    for k, v in tx.get_asset_summary(in_only=True).items():
        assert k == 'Synth:ETH.USDC-0XA0B8'
        assert v == 0.001

    assert tx.is_synth_involved

    non_synth_tx = example_tx_gen('synth_swap.json').txs[2]
    assert not non_synth_tx.is_synth_involved
