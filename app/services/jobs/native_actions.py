import datetime
from collections import defaultdict
from typing import List, Optional

from aioredis import Redis

from proto.access import parse_thor_address, NativeThorTx
from proto.types import MsgDeposit, MsgObservedTxIn
from services.jobs.fetch.native_scan import BlockResult
from services.lib.constants import thor_to_float, NATIVE_RUNE_SYMBOL
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.memo import THORMemo
from services.lib.money import Asset
from services.lib.texts import sep
from services.lib.utils import WithLogger
from services.models.s_swap import parse_swap_and_out_event, StreamingSwap, EventSwapStart, EventOutbound, \
    EventScheduledOutbound, TypeEventSwapAndOut
from services.models.tx import ThorTx, ThorTxType, ThorMetaSwap, SUCCESS


class SwapStartDetector(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    @staticmethod
    def is_rune_asset(asset: str):
        return asset.lower() == 'r' or asset.upper() == NATIVE_RUNE_SYMBOL

    def make_ss_event(self, msg, tx_hash, height) -> Optional[EventSwapStart]:
        ph = self.deps.price_holder

        memo = THORMemo.parse_memo(msg.memo)

        # Must be a swap!
        if not memo or memo.action != ThorTxType.TYPE_SWAP:
            return

        if msg.coins:
            if self.is_rune_asset(memo.asset):
                out_asset_name = NATIVE_RUNE_SYMBOL
            else:
                out_asset_name = ph.pool_fuzzy_first(memo.asset)

            if not out_asset_name:
                self.logger.warning(f'{memo.asset}: asset not found!')
                return

            in_amount = thor_to_float(msg.coins[0].amount)
            in_asset = Asset.from_coin(msg.coins[0])

            if str(in_asset) == NATIVE_RUNE_SYMBOL:
                volume_usd = in_amount * ph.usd_per_rune
            else:
                in_pool_name = ph.pool_fuzzy_first(in_asset.native_pool_name)
                if not in_pool_name:
                    self.logger.warning(f'{in_asset.native_pool_name}: pool if inbound asset not found!')
                    return

                in_pool_info = ph.find_pool(in_pool_name)
                volume_usd = in_amount * in_pool_info.usd_per_asset

            if hasattr(msg, 'from_address'):
                from_address = msg.from_address
            else:
                from_address = parse_thor_address(msg.signer)

            return EventSwapStart(
                StreamingSwap(
                    tx_hash,
                    memo.s_swap_interval,
                    memo.s_swap_quantity,
                    0, 0, memo.limit, 0, 0, 0, [], []
                ),
                from_address=from_address,
                in_amount=thor_to_float(msg.coins[0].amount),
                in_asset=str(in_asset),
                out_asset=out_asset_name,
                expected_rate=thor_to_float(memo.limit),
                volume_usd=volume_usd,
                block_height=height,
                memo=memo
            )

    def handle_deposits(self, txs: List[NativeThorTx], height):
        results = []
        for tx in txs:
            try:
                msg: MsgDeposit = tx.first_message
                if event := self.make_ss_event(msg, tx.hash, height):
                    results.append(event)
            except Exception as e:
                self.logger.error(f'Could not parse DepositTx TX ({tx.hash}): {e!r}')

        return results

    def handle_observed_txs(self, txs: List[NativeThorTx], height):
        # Filter only unique MsgObservedTxIn
        hash_to_tx = {}
        for tx in txs:
            for observed_tx in tx.first_message.txs:
                if (tx_id := observed_tx.tx.id) not in hash_to_tx:
                    hash_to_tx[tx_id] = observed_tx.tx
        txs = list(hash_to_tx.values())

        results = []
        for tx in txs:
            try:
                # Instead of Message there goes just Tx. For this particular test their attributes are compatible!
                if event := self.make_ss_event(tx, tx.id, height):
                    results.append(event)
            except Exception as e:
                self.logger.error(f'Could not parse Observed In TX ({tx.id}): {e!r}')
        return results

    def detect_swaps(self, b: BlockResult):
        deposits = b.find_tx_by_type(MsgDeposit)
        observed_in_txs = b.find_tx_by_type(MsgObservedTxIn)

        # they are based only on memo parsed (just intention, real swap quantity may differ)
        return self.handle_deposits(deposits, b.block_no) + self.handle_observed_txs(observed_in_txs, b.block_no)


class NativeActionExtractor(WithDelegates, INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self._swap_detector = SwapStartDetector(deps)

        self.dbg_watch_swap_id = None

    async def register_new_swaps(self, swaps: List[EventSwapStart], height):
        self.logger.info(f"New swaps {len(swaps)} in block #{height}")

        r: Redis = await self.deps.db.get_redis()

        for swap in swaps:
            if swap.tx_id == self.dbg_watch_swap_id:
                print(f'👿 Start watching swap: {swap}')
                sep()

    async def register_swap_events(self, block: BlockResult, interesting_events: List[TypeEventSwapAndOut]):
        r: Redis = await self.deps.db.get_redis()

        for swap_ev in interesting_events:
            if swap_ev.tx_id == self.dbg_watch_swap_id:
                print(f'👿 new event for watched TX!!! {swap_ev.__class__} at block #{swap_ev.height}')
                print(swap_ev)
                sep()

    @staticmethod
    def get_events_of_interest(block: BlockResult) -> List[TypeEventSwapAndOut]:
        for ev in block.end_block_events:
            swap_ev = parse_swap_and_out_event(ev, height=block.block_no)
            if swap_ev:
                yield swap_ev

    async def on_data(self, sender, block: BlockResult) -> List[ThorTx]:
        new_swaps = self._swap_detector.detect_swaps(block)

        # Incoming swap intentions will be recorded in the DB
        await self.register_new_swaps(new_swaps, block.block_no)

        # Swaps and Outs
        interesting_events = list(self.get_events_of_interest(block))

        # To calculate progress and final slip/fees
        await self.register_swap_events(block, interesting_events)

        return await self.detect_swap_finished(block, interesting_events)

    """
    Kinds of TX
    
    1) THOR => single swap => THOR
    2) THOR => double swap => THOR
    3) OUT => single swap => THOR
    4) OUT => double swap => THOR
    
    5) THOR => single swap [stream] => THOR
    6) THOR => double swap [stream] => THOR
    7) OUT => single swap [stream] => THOR
    8) OUT => double swap [stream] => THOR

    """

    async def detect_swap_finished(self, block: BlockResult, interesting_events: List[TypeEventSwapAndOut]) \
            -> List[ThorTx]:
        """
            We do not wait until scheduled outbound will be sent out.
            Swap end is detected by
                a) EventScheduledOutbound
                b) EventOutbound for Rune/synths
        """
        group_by_in = defaultdict(list)

        for ev in interesting_events:
            if isinstance(ev, (EventOutbound, EventScheduledOutbound)):
                group_by_in[ev.tx_id].append(ev)

        for tx_id, events in group_by_in.items():
            print(f"TX finish {tx_id} => {[e.__class__.__name__ for e in events]}")

        # Build ThorTx
        tx = ThorTx(
            date=int(datetime.datetime.utcnow().timestamp() * 1e9),
            height=block.block_no,
            type=ThorTxType.TYPE_SWAP,
            pools=[],
            in_tx=[],
            out_tx=[],
            meta_swap=ThorMetaSwap(
                liquidity_fee='0',
                network_fees=[],
                trade_slip='0',
                trade_target='0',
                affiliate_fee=0.0,
                memo='',
                affiliate_address='',
                streaming=StreamingSwap(
                    tx_id='',
                    interval=0,
                    quantity=0,
                    count=0,
                    last_height=0,
                    trade_target=0,
                    deposit=0,
                    in_amt=0,
                    out_amt=0,
                    failed_swaps=[],
                    failed_swap_reasons=[]
                )
            ),
            status=SUCCESS
        )

        return []
