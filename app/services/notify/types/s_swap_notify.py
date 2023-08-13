from contextlib import suppress
from typing import List, Optional

from aioredis import Redis

from proto.access import NativeThorTx, parse_thor_address
from proto.types import MsgDeposit, MsgObservedTxIn
from services.jobs.fetch.native_scan import BlockResult
from services.lib.constants import thor_to_float, NATIVE_RUNE_SYMBOL
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.memo import THORMemo
from services.lib.money import Asset
from services.lib.utils import WithLogger
from services.models.s_swap import EventStreamingSwapStart, StreamingSwap
from services.models.tx import ThorTxType


class StreamingSwapStartTxNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer, prefix='thor'):
        super().__init__()
        self.deps = deps
        self.prefix = prefix

    def make_ss_event(self, msg, tx_hash) -> Optional[EventStreamingSwapStart]:
        ph = self.deps.price_holder

        memo = THORMemo.parse_memo(msg.memo)

        # Must be a swap!
        if not memo or memo.action != ThorTxType.TYPE_SWAP:
            return

        if memo.is_streaming and msg.coins:
            out_asset = ph.pool_fuzzy_first(memo.asset)
            if not out_asset:
                self.logger.warning(f'{memo.asset}: asset not found!')
                return

            in_amount = thor_to_float(msg.coins[0].amount)
            in_asset = Asset.from_coin(msg.coins[0])

            # in_asset = Asset.from_string('GAIA/ATOM')  # test for synths

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

            return EventStreamingSwapStart(
                StreamingSwap(
                    tx_hash,
                    memo.s_swap_interval,
                    memo.s_swap_quantity,
                    0, 0, memo.limit, 0, 0, 0, [], []
                ),
                from_address=from_address,
                in_amount=thor_to_float(msg.coins[0].amount),
                in_asset=str(in_asset),
                out_asset=out_asset,
                expected_rate=thor_to_float(memo.limit),
                volume_usd=volume_usd
            )

    def handle_deposits(self, txs: List[NativeThorTx], name='DepositTx'):
        results = []
        for tx in txs:
            try:
                msg: MsgDeposit = tx.first_message
                if event := self.make_ss_event(msg, tx.hash):
                    results.append(event)
            except Exception as e:
                self.logger.error(f'Could not parse DepositTx TX ({tx.hash}): {e!r}')

        return results

    def handle_observed_txs(self, txs: List[NativeThorTx]):
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
                if event := self.make_ss_event(tx, tx.id):
                    results.append(event)
            except Exception as e:
                self.logger.error(f'Could not parse Observed In TX ({tx.id}): {e!r}')
        return results

    def detect_streaming_swaps(self, b: BlockResult):
        deposits = b.find_tx_by_type(MsgDeposit)
        observed_in_txs = b.find_tx_by_type(MsgObservedTxIn)

        # they are based only on memo parsed (just intention, real swap quantity may differ)
        return self.handle_deposits(deposits) + self.handle_observed_txs(observed_in_txs)

    KEY_LAST_SEEN_TX_HASH = 'tx:scanner:streaming-swap:seen-start'

    async def has_seen_hash(self, tx_id: str):
        if tx_id:
            r: Redis = self.deps.db.redis
            return await r.sismember(self.KEY_LAST_SEEN_TX_HASH, tx_id)

    async def mark_as_seen(self, tx_id: str):
        if tx_id:
            r: Redis = self.deps.db.redis
            await r.sadd(self.KEY_LAST_SEEN_TX_HASH, tx_id)

    async def on_data(self, sender, data: BlockResult):
        swaps = self.detect_streaming_swaps(data)
        for swap_start_ev in swaps:
            if not await self.has_seen_hash(tx_id := swap_start_ev.ss.tx_id):
                await self.pass_data_to_listeners(swap_start_ev)
                await self.mark_as_seen(tx_id)

    async def clear_seen_cache(self):
        with suppress(Exception):
            r: Redis = self.deps.db.redis
            await r.delete(self.KEY_LAST_SEEN_TX_HASH)