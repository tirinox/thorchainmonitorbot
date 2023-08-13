from typing import List

from proto.access import NativeThorTx, parse_thor_address
from proto.types import MsgDeposit, MsgObservedTxIn, StreamingSwap
from services.jobs.fetch.native_scan import BlockResult
from services.lib.constants import thor_to_float, NATIVE_RUNE_SYMBOL
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.memo import THORMemo
from services.lib.money import Asset
from services.lib.utils import WithLogger
from services.models.s_swap import EventStreamingSwapStart


class StreamingSwapStartTxNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer, prefix='thor'):
        super().__init__()
        self.deps = deps
        self.prefix = prefix

    def handle_deposits(self, txs: List[NativeThorTx]):
        ph = self.deps.price_holder

        results = []
        for tx in txs:
            try:
                msg: MsgDeposit = tx.first_message
                memo = THORMemo.parse_memo(msg.memo)
                if memo.is_streaming and msg.coins:
                    out_asset = ph.pool_fuzzy_first(memo.asset)
                    if not out_asset:
                        self.logger.warning(f'{memo.asset}: asset not found!')
                        continue

                    in_amount = thor_to_float(msg.coins[0].amount)
                    in_asset = Asset.from_coin(msg.coins[0])

                    # in_asset = Asset.from_string('GAIA/ATOM')  # test for synths

                    if str(in_asset) == NATIVE_RUNE_SYMBOL:
                        volume_usd = in_amount * ph.usd_per_rune
                    else:
                        in_pool_name = ph.pool_fuzzy_first(in_asset.native_pool_name)
                        if not in_pool_name:
                            self.logger.warning(f'{in_asset.native_pool_name}: pool if inbound asset not found!')
                            continue

                        in_pool_info = ph.find_pool(in_pool_name)
                        volume_usd = in_amount * in_pool_info.usd_per_asset

                    results.append(EventStreamingSwapStart(
                        StreamingSwap(
                            tx.hash,
                            memo.s_swap_interval,
                            memo.s_swap_quantity
                        ),
                        from_address=parse_thor_address(msg.signer),
                        in_amount=thor_to_float(msg.coins[0].amount),
                        in_asset=str(in_asset),
                        out_asset=out_asset,
                        expected_rate=thor_to_float(memo.limit),
                        volume_usd=volume_usd
                    ))

            except Exception as e:
                self.logger.error(f'Could not parse deposit TX ({tx.hash}): {e!r}')

        return results

    def handle_observed_txs(self, txs: List[NativeThorTx]):
        # Filter only unique MsgObservedTxIn
        hash_to_tx = {}
        for tx in txs:
            if (tx_id := tx.hash) not in hash_to_tx:
                hash_to_tx[tx_id] = tx
        txs = list(hash_to_tx.values())

        results = []
        for tx in txs:
            ...

        return results

    def detect_streaming_swaps(self, b: BlockResult):
        deposits = b.find_tx_by_type(MsgDeposit)
        observed_in_txs = b.find_tx_by_type(MsgObservedTxIn)

        return self.handle_deposits(deposits) + self.handle_observed_txs(observed_in_txs)

    async def on_data(self, sender, data: BlockResult):
        swaps = self.detect_streaming_swaps(data)
        for swap_start_ev in swaps:
            await self.pass_data_to_listeners(swap_start_ev)
