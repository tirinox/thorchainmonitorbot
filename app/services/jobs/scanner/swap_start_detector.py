from typing import Optional, List

from proto.access import parse_thor_address, NativeThorTx
from proto.types import MsgDeposit, MsgObservedTxIn
from services.jobs.scanner.native_scan import BlockResult
from services.lib.constants import NATIVE_RUNE_SYMBOL, thor_to_float
from services.lib.depcont import DepContainer
from services.lib.memo import THORMemo
from services.lib.money import is_rune_asset, Asset
from services.lib.utils import WithLogger
from services.models.s_swap import EventSwapStart, StreamingSwap
from services.models.tx import ThorTxType


class SwapStartDetector(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    def make_ss_event(self, msg, tx_hash, height) -> Optional[EventSwapStart]:
        ph = self.deps.price_holder

        memo = THORMemo.parse_memo(msg.memo)

        # Must be a swap!
        if not memo or memo.action != ThorTxType.TYPE_SWAP:
            return

        if msg.coins:
            if is_rune_asset(memo.asset):
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
                memo=memo,
                memo_str=msg.memo,  # original memo
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
