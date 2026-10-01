from typing import cast
from types import SimpleNamespace

import pytest

from jobs.scanner.block_result import BlockResult
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




TRON_USDT = 'TRON.USDT-TR7NHQJEKQXGTCI8Q8ZY4PL8OTSZGJLJ6T'


def make_observed_outbound_tx(in_tx_id: str, out_id: str, amount: int, *, accepted: bool):
    """An observation of an L1 outbound; once the chain accepts it, the tx result carries an "outbound" event."""
    memo = f'OUT:{in_tx_id}'
    events = [{
        'type': 'outbound',
        'id': out_id,
        'in_tx_id': in_tx_id,
        'chain': 'TRON',
        'from': 'TVaultAddress',
        'to': 'TUserAddress',
        'coin': f'{amount} {TRON_USDT}',
        'memo': memo,
    }] if accepted else []
    return {
        'hash': f'NATIVE-{out_id}',
        'tx': {'messages': [{
            '@type': '/types.MsgObservedTxQuorum',
            'quoTx': {
                'obsTx': {
                    'tx': {
                        'id': out_id,
                        'chain': 'TRON',
                        'from_address': 'TVaultAddress',
                        'to_address': 'TUserAddress',
                        'coins': [{'asset': TRON_USDT, 'amount': str(amount), 'decimals': '6'}],
                        'gas': [],
                        'memo': memo,
                    },
                    'status': 'incomplete',
                    'out_hashes': [],
                    'block_height': '84341306',
                    'finalise_height': '84341306',
                },
                'inbound': False,
            },
        }]},
        'result': {'code': 0, 'events': events},
    }


def make_block(height: int, txs: list):
    return BlockResult.load_block({
        'header': {'time': '2026-07-10T06:21:19.607Z'},
        'txs': txs,
        'begin_block_events': [],
        'end_block_events': [],
    }, height)


@pytest.mark.asyncio
async def test_outbound_attempt_the_chain_did_not_accept_is_not_counted(monkeypatch):
    # 26D5E260...: leg 2 was observed from one vault but never accepted, then rescheduled and sent by another vault;
    # both observations were summed, and the alert showed 436.8K USDT out of 265.6K
    deps = make_deps(stages={'outbound_signed': {'completed': False}})
    extractor = SwapExtractorBlock(deps)

    async def no_new_swaps(_block):
        return []

    monkeypatch.setattr(extractor, 'register_new_swaps', no_new_swaps)

    tx_id = '26D5E260244B1B8299B7EC8A48394D81088C7AEE22DD500899A2DACC8B310A42'
    await extractor._db.write_tx_status_kw(
        tx_id,
        id=tx_id,
        status=SwapProps.STATUS_OBSERVED_IN,
        memo='=:TRON.USDT:TUserAddress:0/1/0',
        from_address='0x206698dcab42174cf0e8da81bc1662ebf34ccf13',
        in_amount='15014200000',
        in_asset='ETH.ETH',
        out_asset=TRON_USDT,
        block_height=26941941,
    )
    await extractor.register_swap_events(SimpleNamespace(block_no=26944835), [
        parse_swap_and_out_event(make_swap_event(tx_id, 26944835, out_asset=TRON_USDT)),
    ])

    leg_1, leg_2 = 9436391688400, 17122382108500
    assert await extractor.on_data(None, make_block(26944845, [
        make_observed_outbound_tx(tx_id, 'C4FF1F43C1F4BDEC566679BAEF1A702C4AC6460994B878B8554219AD4B993844', leg_1,
                                  accepted=True),
        make_observed_outbound_tx(tx_id, '6C2C9FCDE12444B45BB0496209A81B70D43DD732FBEA89638C4E9EEDE1096120', leg_2,
                                  accepted=False),
    ])) == []

    deps.thor_connector.stages = {'outbound_signed': {'completed': True}}
    txs = await extractor.on_data(None, make_block(26946347, [
        make_observed_outbound_tx(tx_id, '2CA14FF9E6A47A36304795A2FEAFB2518E60C721A2A7B9627928FFB0291F4A8D', leg_2,
                                  accepted=True),
    ]))

    assert len(txs) == 1
    out = txs[0].recipients_output
    assert out.address == 'TUserAddress'
    assert [(c.amount, c.asset) for c in out.coins] == [(leg_1 + leg_2, TRON_USDT)]
