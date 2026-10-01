"""
AggregatorDataExtractor: DEX aggregator detection on both ends of a swap.
The EVM chains are replaced with fakes, so no RPC is touched.
"""
import copy
import json
from typing import Optional

import pytest
from web3.exceptions import TransactionNotFound

from api.w3.aggregator import AggregatorDataExtractor, is_evm_tx_hash
from api.w3.token_record import AmountToken, TokenRecord, SwapInOut, DEX_SOURCE_MEMO, DEX_SOURCE_CHAIN, \
    DEX_SOURCE_MEMO_AND_CHAIN
from comm.localization.eng_base import BaseLocalization
from lib.config import Config
from lib.constants import Chains
from lib.depcont import DepContainer
from models.asset import Asset
from models.memo import THORMemo
from models.tx import ThorAction, ThorSubTx, ThorCoin
from tools.lib.lp_common import LpAppFramework, load_sample_txs

LpAppFramework.solve_working_dir_mess()

ETH_TOKEN = TokenRecord('0xa5f2211B9b8170F694421f2046281775E8468044', 1, 18, 'THORSwapToken', 'THOR', '')
AVAX_TOKEN = TokenRecord('0xb97ef9ef8734c71904d8002f8b6bc66dd9c48a6e', 43114, 6, 'USD Coin', 'USDC', '')

OUT_TX_HASH = '926BC5212732BB863EE77D40A504BCA9583CF6D2F07090E2A3C468CFE6947357'
IN_EVM_TX_HASH = '0xc2483005204f9b4d41d15024913807bc8d2a1714c55fae0b5f23b1d71d6affe3'


class FakeChain:
    """Stands in for AggregatorSingleChain: records the calls and answers with canned data."""

    def __init__(self, chain: str, token: Optional[TokenRecord]):
        self.chain = chain
        self.l1_asset = str(Asset.gas_asset_from_chain(chain))
        self.token = token
        self.calls = []
        self.fail_memo = False
        self.chain_out_result: Optional[AmountToken] = AmountToken(
            17596.39, token, aggr_name='TSAggregatorGeneric', aggr_address='0x0F2CD5dF82959e00BE7AfeeF8245900FC4414199',
            token_address=token.address if token else '', chain=chain, source=DEX_SOURCE_CHAIN,
            recipient='0x1e240f76bcf08219e70b2c3c20f20f5ec4b43585',
        )
        self.chain_in_result: Optional[AmountToken] = AmountToken(
            1000.0, token, aggr_name='TSAggregatorUniswapV2', aggr_address='0x14D52a5709743C9563a2C36842B3Fe7Db1fCf5bc',
            token_address=token.address if token else '', chain=chain, source=DEX_SOURCE_CHAIN,
        )

    def resolve_aggregator(self, query):
        self.calls.append(('resolve_aggregator', query))
        return (query[-6:] + '…', query) if query else ('', '')

    async def describe_swap_out_from_memo(self, memo: THORMemo):
        self.calls.append(('memo', memo.dex_aggregator_address, memo.final_asset_address))
        if self.fail_memo:
            raise RuntimeError('token list is down')
        if not memo.uses_aggregator_out:
            return None
        name, address = self.resolve_aggregator(memo.dex_aggregator_address)
        return AmountToken(None, self.token, aggr_name=name, aggr_address=address,
                           token_address=memo.final_asset_address, chain=self.chain, source=DEX_SOURCE_MEMO)

    async def decode_swap_out(self, tx_hash):
        self.calls.append(('chain_out', tx_hash))
        if self.chain_out_result is None:
            raise TransactionNotFound('not swap out')
        return self.chain_out_result

    async def decode_swap_in(self, tx_hash):
        self.calls.append(('chain_in', tx_hash))
        if self.chain_in_result is None:
            raise TransactionNotFound('not swap in')
        return self.chain_in_result


class FakePriceHolder:
    usd_per_rune = 5.0

    def convert_to_usd(self, amount, asset):
        if asset == 'THOR.RUNE':
            return amount * self.usd_per_rune
        if asset == 'AVAX.AVAX':
            return amount * 20.0
        return None


class FakePoolCache:
    def __init__(self, ph):
        self.ph = ph

    async def get(self):
        return self.ph


class Sink:
    def __init__(self):
        self.received = []

    async def on_data(self, sender, data):
        self.received.append(data)


def make_extractor(with_prices=True, min_usd=500.0):
    cfg = Config(data={
        'web3': {'timeout': '5s'},
        'tx': {'swap': {'also_trigger_when': {'dex_aggregator_used': {'min_usd_total': min_usd}}}},
    })
    deps = DepContainer(cfg=cfg)
    deps.pool_cache = FakePoolCache(FakePriceHolder()) if with_prices else None
    extractor = AggregatorDataExtractor(deps, suitable_chains=())  # no real chains (no RPC in the config)
    eth, avax = FakeChain(Chains.ETH, ETH_TOKEN), FakeChain(Chains.AVAX, AVAX_TOKEN)
    extractor.asset_to_aggr = {eth.l1_asset: eth, avax.l1_asset: avax}
    return extractor, eth, avax


@pytest.fixture
def eth_swap_out_tx() -> ThorAction:
    # RUNE -> ETH.ETH -> (aggregator FC4414199) -> THOR token
    return load_sample_txs('tests/sample_data/example_eth_swap_out.json')[0]


def with_memo(tx: ThorAction, memo: str) -> ThorAction:
    tx = copy.deepcopy(tx)
    tx.meta_swap.memo = memo
    return tx


# ---- helpers ----

def test_is_evm_tx_hash():
    assert is_evm_tx_hash(OUT_TX_HASH)
    assert is_evm_tx_hash(IN_EVM_TX_HASH)
    assert not is_evm_tx_hash('')
    assert not is_evm_tx_hash(None)
    assert not is_evm_tx_hash('0xdeadbeef')
    assert not is_evm_tx_hash('thor1w2p7nya3880s04adt7d4498lsz6762lg2vuke5')


def test_get_by_asset_accepts_abbreviations():
    extractor, eth, avax = make_extractor()
    assert extractor.get_by_asset('ETH.ETH') is eth
    assert extractor.get_by_asset('e') is eth
    assert extractor.get_by_asset('a') is avax
    assert extractor.get_by_asset('AVAX.AVAX') is avax
    assert extractor.get_by_asset('BTC.BTC') is None
    assert extractor.get_by_asset('') is None
    assert extractor.get_by_chain('ETH') is eth
    assert extractor.get_by_chain('BTC') is None


# ---- swap out ----

@pytest.mark.asyncio
async def test_swap_out_from_memo_when_outbound_is_not_there_yet(eth_swap_out_tx):
    extractor, eth, avax = make_extractor()
    tx = copy.deepcopy(eth_swap_out_tx)
    tx.out_tx = []  # pending / streaming: nothing has left THORChain yet
    tx.status = 'pending'

    info = await extractor.detect(tx, FakePriceHolder())

    assert info.swap_in is None
    out = info.swap_out
    assert out is not None
    assert out.source == DEX_SOURCE_MEMO
    assert out.chain == 'ETH'
    assert out.token == ETH_TOKEN
    assert out.symbol == 'THOR'
    assert out.aggr_address == 'FC4414199'
    assert out.aggr_name
    assert out.amount is None and not out.has_amount
    assert ('chain_out', OUT_TX_HASH) not in eth.calls


@pytest.mark.asyncio
async def test_swap_out_memo_enriched_on_chain_above_threshold(eth_swap_out_tx):
    extractor, eth, avax = make_extractor(min_usd=500)
    # 2000 RUNE in at $5 = $10000 >= $500 -> the outbound is decoded on-chain
    info = await extractor.detect(eth_swap_out_tx, FakePriceHolder())

    out = info.swap_out
    assert ('chain_out', OUT_TX_HASH) in eth.calls
    assert out.source == DEX_SOURCE_MEMO_AND_CHAIN
    assert out.amount == pytest.approx(17596.39)
    assert out.recipient == '0x1e240f76bcf08219e70b2c3c20f20f5ec4b43585'
    assert out.aggr_address == '0x0F2CD5dF82959e00BE7AfeeF8245900FC4414199'  # full address from the chain
    assert out.aggr_name.endswith('…')  # the memo name is kept
    assert out.token == ETH_TOKEN


@pytest.mark.asyncio
async def test_swap_out_no_chain_decode_below_threshold(eth_swap_out_tx):
    extractor, eth, avax = make_extractor(min_usd=1_000_000)
    info = await extractor.detect(eth_swap_out_tx, FakePriceHolder())

    assert info.swap_out.source == DEX_SOURCE_MEMO
    assert info.swap_out.amount is None
    assert not any(c[0] == 'chain_out' for c in eth.calls)


@pytest.mark.asyncio
async def test_swap_out_no_chain_decode_without_prices(eth_swap_out_tx):
    extractor, eth, avax = make_extractor(with_prices=False)
    info = await extractor.detect(eth_swap_out_tx, None)

    assert info.swap_out.source == DEX_SOURCE_MEMO
    assert not any(c[0] == 'chain_out' for c in eth.calls)


@pytest.mark.asyncio
async def test_swap_out_chain_decode_when_there_is_no_memo(eth_swap_out_tx):
    extractor, eth, avax = make_extractor()
    tx = copy.deepcopy(eth_swap_out_tx)
    tx.meta_swap = None  # no memo at all: only the chain can tell

    info = await extractor.detect(tx, FakePriceHolder())

    assert ('chain_out', OUT_TX_HASH) in eth.calls
    assert info.swap_out.source == DEX_SOURCE_CHAIN
    assert info.swap_out.amount == pytest.approx(17596.39)


@pytest.mark.asyncio
async def test_swap_out_keeps_memo_leg_when_chain_says_no(eth_swap_out_tx):
    extractor, eth, avax = make_extractor()
    eth.chain_out_result = None  # TransactionNotFound
    info = await extractor.detect(eth_swap_out_tx, FakePriceHolder())

    assert ('chain_out', OUT_TX_HASH) in eth.calls
    assert info.swap_out.source == DEX_SOURCE_MEMO
    assert info.swap_out.token == ETH_TOKEN


@pytest.mark.asyncio
async def test_swap_out_none_when_memo_has_no_aggregator(eth_swap_out_tx):
    extractor, eth, avax = make_extractor()
    tx = with_memo(eth_swap_out_tx, '=:ETH.ETH:0x1e240f76bcf08219e70b2c3c20f20f5ec4b43585:0/1/1')

    info = await extractor.detect(tx, FakePriceHolder())

    assert info.swap_out is None
    assert not any(c[0] == 'chain_out' for c in eth.calls)


@pytest.mark.asyncio
async def test_swap_out_none_for_non_evm_target(eth_swap_out_tx):
    extractor, eth, avax = make_extractor()
    tx = with_memo(eth_swap_out_tx, '=:BTC.BTC:bc1q69fyncf9x8spcqcsvtq5ek74jysye5dj4zg6l8:0::0:FC4414199:5e8468044')
    tx.out_tx = [ThorSubTx('bc1q69fyncf9x8spcqcsvtq5ek74jysye5dj4zg6l8', [ThorCoin(100000, 'BTC.BTC')], 'ABCD')]

    info = await extractor.detect(tx, FakePriceHolder())

    assert info == SwapInOut(None, None)
    assert eth.calls == [] and avax.calls == []


@pytest.mark.asyncio
async def test_swap_out_chain_from_memo_abbreviation(eth_swap_out_tx):
    extractor, eth, avax = make_extractor()
    tx = with_memo(eth_swap_out_tx, '=:a:0x1e240f76bcf08219e70b2c3c20f20f5ec4b43585:0::0:47F9bf5a:9c48a6e')
    tx.out_tx = []

    info = await extractor.detect(tx, FakePriceHolder())

    assert info.swap_out.chain == 'AVAX'
    assert info.swap_out.token == AVAX_TOKEN
    assert eth.calls == []


@pytest.mark.asyncio
async def test_swap_out_skips_chain_decode_when_out_hash_is_the_inbound_hash(eth_swap_out_tx):
    # The block scanner may put the inbound hash into the outbound before the outbound is signed
    extractor, eth, avax = make_extractor()
    tx = copy.deepcopy(eth_swap_out_tx)
    tx.out_tx[0].tx_id = tx.in_tx[0].tx_id

    info = await extractor.detect(tx, FakePriceHolder())

    assert info.swap_out.source == DEX_SOURCE_MEMO
    assert not any(c[0] == 'chain_out' for c in eth.calls)


@pytest.mark.asyncio
async def test_swap_out_falls_back_to_bare_memo_facts_when_token_list_fails(eth_swap_out_tx):
    extractor, eth, avax = make_extractor(with_prices=False)
    eth.fail_memo = True

    info = await extractor.detect(eth_swap_out_tx, None)

    out = info.swap_out
    assert out is not None
    assert out.token is None
    assert out.token_address == '5e8468044'
    assert out.symbol == '5e8468044'
    assert out.aggr_address == 'FC4414199'
    assert out.source == DEX_SOURCE_MEMO


# ---- swap in ----

@pytest.mark.asyncio
async def test_swap_in_detected_on_evm_input():
    extractor, eth, avax = make_extractor()
    txs = load_sample_txs('tests/sample_data/example_avax_swap_in.json')  # AVAX.AVAX -> RUNE
    tx = txs[0]

    info = await extractor.detect(tx, FakePriceHolder())

    assert ('chain_in', tx.in_tx[0].tx_id) in avax.calls
    assert info.swap_in == avax.chain_in_result
    assert info.swap_in.chain == 'AVAX'
    assert info.swap_out is None


@pytest.mark.asyncio
async def test_swap_in_none_when_not_an_aggregator_call():
    extractor, eth, avax = make_extractor()
    avax.chain_in_result = None
    tx = load_sample_txs('tests/sample_data/example_avax_swap_in.json')[0]

    info = await extractor.detect(tx, FakePriceHolder())

    assert info.swap_in is None


# ---- pipeline ----

@pytest.mark.asyncio
async def test_batch_survives_a_broken_tx(eth_swap_out_tx):
    extractor, eth, avax = make_extractor()
    sink = Sink()
    extractor.add_subscriber(sink)

    broken = copy.deepcopy(eth_swap_out_tx)
    broken.in_tx = None  # will blow up inside the detection
    good = copy.deepcopy(eth_swap_out_tx)
    not_a_swap = copy.deepcopy(eth_swap_out_tx)
    not_a_swap.type = 'addLiquidity'

    batch = [broken, good, not_a_swap]
    await extractor.on_data(None, batch)

    assert sink.received == [batch]  # everything passed through
    assert good.dex_info.swap_out is not None
    assert good.dex_aggregator_used
    assert not not_a_swap.dex_aggregator_used
    assert broken.dex_info == SwapInOut()


@pytest.mark.asyncio
async def test_pipeline_passes_through_without_chains(eth_swap_out_tx):
    cfg = Config(data={})
    extractor = AggregatorDataExtractor(DepContainer(cfg=cfg))  # no web3 rpc configured -> no chains
    assert extractor.asset_to_aggr == {}
    sink = Sink()
    extractor.add_subscriber(sink)

    await extractor.on_data(None, [eth_swap_out_tx])

    assert sink.received == [[eth_swap_out_tx]]
    assert not eth_swap_out_tx.dex_aggregator_used


def test_estimate_usd_volume(eth_swap_out_tx):
    ph = FakePriceHolder()
    assert AggregatorDataExtractor.estimate_usd_volume(eth_swap_out_tx, ph) == pytest.approx(2000 * 5.0)
    eth_swap_out_tx.full_volume_in_rune = 100.0
    assert AggregatorDataExtractor.estimate_usd_volume(eth_swap_out_tx, ph) == pytest.approx(500.0)
    assert AggregatorDataExtractor.estimate_usd_volume(eth_swap_out_tx, None) is None


# ---- AmountToken ----

def test_amount_token_json_roundtrip():
    leg = AmountToken(None, ETH_TOKEN, aggr_name='TSAggregatorGeneric', aggr_address='0x0F2C', token_address='5e8468044',
                      chain='ETH', source=DEX_SOURCE_MEMO, recipient='0x1e24')
    restored = AmountToken.from_json(json.dumps(leg.as_json))
    assert restored.amount is None
    assert restored.symbol == 'THOR'
    assert restored.aggr_name == 'TSAggregatorGeneric'
    assert restored.aggr_address == '0x0F2C'
    assert restored.token_address == '5e8468044'
    assert restored.chain == 'ETH'
    assert restored.source == DEX_SOURCE_MEMO
    assert restored.recipient == '0x1e24'

    leg = leg._replace(amount=12.5)
    assert AmountToken.from_json(leg.as_json).amount == 12.5


def test_amount_token_from_legacy_json():
    # Before: memo-based swap outs were stored with amount = -1 and only a symbol
    legacy = json.dumps({'amount': -1, 'aggr_name': 'TSAggregatorGeneric', 'symbol': 'THOR'})
    restored = AmountToken.from_json(legacy)
    assert restored is not None
    assert restored.amount is None
    assert restored.symbol == 'THOR'
    assert restored.aggr_name == 'TSAggregatorGeneric'

    assert AmountToken.from_json('null') is None
    assert AmountToken.from_json('') is None
    assert AmountToken.from_json('{"amount": 0}') is None
    assert AmountToken.from_json('garbage') is None


def test_amount_token_symbol_without_token():
    assert AmountToken(None, None).symbol == '?'
    assert AmountToken(None, None, token_address='0xa5f2211B9b8170F694421f2046281775E8468044').symbol == '0xa5f2…8044'
    assert AmountToken(None, None, token_address='5e8468044').symbol == '5e8468044'
    assert not AmountToken(None, None).is_known
    assert AmountToken(None, None, aggr_name='x').is_known


def test_amount_token_merge_on_chain():
    memo_leg = AmountToken(None, None, aggr_name='FC44…', aggr_address='FC4414199', token_address='5e8468044',
                           chain='ETH', source=DEX_SOURCE_MEMO)
    chain_leg = AmountToken(10.0, ETH_TOKEN, aggr_name='TSAggregatorGeneric', aggr_address='0x0F2C',
                            token_address=ETH_TOKEN.address, chain='ETH', source=DEX_SOURCE_CHAIN, recipient='0x1e24')
    merged = memo_leg.merge_on_chain(chain_leg)
    assert merged.amount == 10.0
    assert merged.token == ETH_TOKEN
    assert merged.aggr_name == 'FC44…'  # memo name wins when both are there
    assert merged.aggr_address == '0x0F2C'
    assert merged.recipient == '0x1e24'
    assert merged.source == DEX_SOURCE_MEMO_AND_CHAIN
    assert memo_leg.merge_on_chain(None) is memo_leg


# ---- formatting ----

class Loc(BaseLocalization):
    pass


def test_format_aggregator_tolerates_unknowns():
    loc = Loc(Config(data={}))
    assert loc.format_aggregator(AmountToken(None, ETH_TOKEN, chain='ETH')) == 'ETH.THOR'
    assert loc.format_aggregator(AmountToken(None, ETH_TOKEN)) == 'ETH.THOR'  # chain from the token's chain id
    assert loc.format_aggregator(AmountToken(None, None, token_address='5e8468044', chain='ETH')) == 'ETH.5e8468044'
    assert loc.format_aggregator(AmountToken(None, None)) == '?'
    with_amount = loc.format_aggregator(AmountToken(12.5, AVAX_TOKEN, chain='AVAX'))
    assert with_amount.endswith('AVAX.USDC') and '12.5' in with_amount


def test_format_swap_route_both_ends(eth_swap_out_tx):
    loc = Loc(Config(data={}))
    tx = copy.deepcopy(eth_swap_out_tx)
    tx.dex_info = SwapInOut(
        AmountToken(1000.0, AVAX_TOKEN, aggr_name='TSAggregatorTraderJoe', chain='AVAX'),
        AmountToken(None, ETH_TOKEN, aggr_name='TSAggregatorGeneric', chain='ETH'),
    )
    route = loc.format_swap_route(tx, usd_per_rune=5.0)
    assert 'AVAX.USDC' in route
    assert 'TSAggregatorTraderJoe' in route
    assert 'TSAggregatorGeneric' in route
    assert route.index('TSAggregatorTraderJoe') < route.index('⚡') < route.index('TSAggregatorGeneric')
    assert route.rstrip().endswith('ETH.THOR') or 'ETH.THOR (' in route
