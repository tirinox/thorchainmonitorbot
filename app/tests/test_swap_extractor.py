from typing import cast
from types import SimpleNamespace

import pytest

from jobs.scanner.swap_extractor import SwapExtractorBlock
from jobs.scanner.swap_props import SwapProps
from jobs.scanner.tx import ThorEvent
from lib.db import DB
from lib.depcont import DepContainer
from models.events import parse_swap_and_out_event
from tests.fakes import FakeDB, FakeRedis


class DummyCfg:
    @staticmethod
    def as_interval(_key, _default):
        return 3 * 24 * 60 * 60


class DummyLastBlockCache:
    @staticmethod
    async def get_timestamp_of_block(_height):
        return 1_700_000_000


class DummyThorConnector:
    def __init__(self, stages=None):
        self.stages = stages
        self.called = False

    async def query_tx_stages(self, _tx_id, _height=None):
        self.called = True
        return self.stages


def make_deps(*, stages=None) -> DepContainer:
    deps = DepContainer()
    deps.db = cast(DB, cast(object, FakeDB(FakeRedis())))
    deps.cfg = cast(object, DummyCfg())
    deps.last_block_cache = cast(object, DummyLastBlockCache())
    deps.thor_connector = cast(object, DummyThorConnector(stages=stages))
    return deps


def make_swap_event(tx_id: str, height: int, *, out_asset: str = 'THOR.RUNE'):
    return ThorEvent.from_dict({
        'type': 'swap',
        'id': tx_id,
        'pool': 'BSC.USDT-0X55D398326F99059FF775485246999027B3197955',
        'swap_target': '0',
        'swap_slip': '10',
        'liquidity_fee': '1128480757',
        'liquidity_fee_in_rune': '1128480757',
        'emit_asset': '16507524163 THOR.RUNE',
        'streaming_swap_count': '2',
        'streaming_swap_quantity': '11',
        'chain': 'BSC',
        'from': '0x1566ce23ea850df05d50768d52ea93644f293559',
        'to': '0x070eEF0485B782C2906Bd620B1Fe12Ce72295f59',
        'coin': '9955727273 BSC.USDT-0X55D398326F99059FF775485246999027B3197955',
        'memo': '=:r:thor1l5kntynwr0cfpvjaxsarxrjglxhs7vcuvpaa4w:181401823033:sto:0',
        'out_asset': out_asset,
    }, height=height)


def make_outbound_event(tx_id: str, height: int, *, coin: str = '181624641261 THOR.RUNE', chain: str = 'THOR'):
    return ThorEvent.from_dict({
        'type': 'outbound',
        'in_tx_id': tx_id,
        'id': '0000000000000000000000000000000000000000000000000000000000000000',
        'chain': chain,
        'from': 'thor1g98cy3n9mmjrpn0sxmn63lztelera37n8n67c0',
        'to': 'thor1l5kntynwr0cfpvjaxsarxrjglxhs7vcuvpaa4w',
        'coin': coin,
        'memo': f'OUT:{tx_id}',
    }, height=height)


async def store_completed_swap(extractor: SwapExtractorBlock, tx_id: str, *, out_asset: str, outbound_coin: str, outbound_chain: str):
    await extractor._db.write_tx_status_kw(
        tx_id,
        id=tx_id,
        status=SwapProps.STATUS_OBSERVED_IN,
        memo='=:r:thor1l5kntynwr0cfpvjaxsarxrjglxhs7vcuvpaa4w:181401823033:sto:0',
        from_address='0x1566ce23ea850df05d50768d52ea93644f293559',
        in_amount='109513000000',
        in_asset='BSC.USDT-0X55D398326F99059FF775485246999027B3197955',
        out_asset=out_asset,
        block_height=26130215,
    )
    swap_event = parse_swap_and_out_event(make_swap_event(tx_id, 26130215, out_asset=out_asset))
    outbound_event = parse_swap_and_out_event(make_outbound_event(tx_id, 26130220, coin=outbound_coin, chain=outbound_chain))
    block = SimpleNamespace(block_no=26130220)
    await extractor.register_swap_events(block, [swap_event])
    await extractor.register_swap_events(block, [outbound_event])


@pytest.mark.asyncio
async def test_handle_finished_swaps_does_not_wait_for_tx_stages_on_native_rune_outbound():
    deps = make_deps(stages=None)
    extractor = SwapExtractorBlock(deps)
    tx_id = '220DB364FB625F7570A7C1C5B56831A22F88405F3713453908EBFFD0C7A627C4'
    await store_completed_swap(
        extractor,
        tx_id,
        out_asset='THOR.RUNE',
        outbound_coin='181624641261 THOR.RUNE',
        outbound_chain='THOR',
    )

    txs = await extractor.handle_finished_swaps({tx_id}, 26130220)
    saved = await extractor._db.read_tx_status(tx_id)

    assert len(txs) == 1
    assert txs[0].tx_hash == tx_id
    assert saved.status == SwapProps.STATUS_GIVEN_AWAY
    assert deps.thor_connector.called is False


@pytest.mark.asyncio
async def test_handle_finished_swaps_still_checks_tx_stages_for_non_rune_l1_outbound():
    deps = make_deps(stages=None)
    extractor = SwapExtractorBlock(deps)
    tx_id = 'BTC-OUTBOUND-TX'
    await store_completed_swap(
        extractor,
        tx_id,
        out_asset='BTC.BTC',
        outbound_coin='8277724 BTC.BTC',
        outbound_chain='BTC',
    )

    txs = await extractor.handle_finished_swaps({tx_id}, 26130220)
    saved = await extractor._db.read_tx_status(tx_id)

    assert txs == []
    assert saved.status == SwapProps.STATUS_OBSERVED_IN
    assert deps.thor_connector.called is True


