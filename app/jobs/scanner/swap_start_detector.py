from typing import Optional, List

from jobs.scanner.native_scan import BlockResult
from jobs.scanner.tx import NativeThorTx, ThorTxMessage
from lib.constants import NATIVE_RUNE_SYMBOL, thor_to_float
from lib.depcont import DepContainer
from lib.utils import WithLogger, safe_get
from models.asset import Asset, is_rune
from models.memo import ActionType
from models.memo import THORMemo
from models.s_swap import StreamingSwap, AlertSwapStart


# from proto.access import NativeThorTx
# from proto.types import MsgDeposit, MsgObservedTxIn


class SwapStartDetector(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    def make_swap_start_event(self, msg: dict, tx_hash, height, is_deposit) -> Optional[AlertSwapStart]:
        """
        msg is a dict, either MsgDeposit.messages[i] or MsgObservedTxIn.messages[i].txs[j].tx
        """
        memo_str = msg['memo']
        memo = THORMemo.parse_memo(memo_str, no_raise=True)

        # Must be a swap!
        if not memo or memo.action != ActionType.SWAP:
            return

        if not (coins := msg.get('coins')):
            self.logger.error(f'No coins in swap tx: {msg}')
            return

        prices = self.deps.price_holder

        if is_rune(memo.asset):
            out_asset_name = NATIVE_RUNE_SYMBOL
        else:
            out_asset_name = prices.pool_fuzzy_first(memo.asset, restore_type=True)

        if not out_asset_name:
            self.logger.warning(f'{memo.asset}: asset not found!')
            return

        # get data
        amount = coins[0]['amount']
        in_amount = thor_to_float(amount)
        in_asset = Asset.from_string(coins[0]["asset"])
        from_address = msg.get('from_address', None) or msg.get('signer', '')

        if str(in_asset) == NATIVE_RUNE_SYMBOL:
            volume_usd = in_amount * prices.usd_per_rune
        else:
            in_pool_name = prices.pool_fuzzy_first(in_asset.native_pool_name)
            if not in_pool_name:
                self.logger.warning(f'{in_asset.native_pool_name}: pool if inbound asset not found!')
                return

            in_pool_info = prices.find_pool(in_pool_name)
            volume_usd = in_amount * in_pool_info.usd_per_asset

            if is_deposit and not in_asset.is_synth:
                # It is not a synth, but it is deposited by a native tx? hm... is it real? Ah, must be TRADE ASSET!
                in_asset.is_trade = True

        return AlertSwapStart(
            StreamingSwap(
                tx_hash,
                memo.s_swap_interval,
                memo.s_swap_quantity,
                0, 0, memo.limit, 0, '', 0, '', 0, '', [], [],
            ),
            from_address=from_address,
            in_amount=int(amount),
            in_asset=str(in_asset),
            out_asset=out_asset_name,
            expected_rate=int(memo.limit),
            volume_usd=volume_usd,
            block_height=height,
            memo=memo,
            memo_str=memo_str,  # original memo
        )

    def handle_deposits(self, txs: List[NativeThorTx], height):
        results = []
        for tx in txs:
            for msg in tx.messages:
                try:
                    if event := self.make_swap_start_event(msg.attrs, tx.tx_hash, height, is_deposit=True):
                        results.append(event)
                except Exception as e:
                    self.logger.error(f'Could not parse DepositTx TX ({tx.tx_hash}): {e!r}')

        return results

    def _filter_unique_observed_txs(self, txs: List[NativeThorTx]):
        # Filter only unique MsgObservedTxIn
        hash_to_tx = {}
        for tx in txs:
            if message_txs := tx.first_message.txs:
                for observed_tx in message_txs:
                    if (tx_id := safe_get(observed_tx, 'tx', 'id')) not in hash_to_tx:
                        hash_to_tx[tx_id] = observed_tx['tx']
            else:
                self.logger.error(f'No txs in MsgObservedTxIn: {tx}. Impossible?')
        return hash_to_tx

    def handle_observed_txs(self, txs: List[NativeThorTx], height: int):
        observed_txs_dicts = self._filter_unique_observed_txs(txs)

        for tx_hash, tx in observed_txs_dicts.items():
            try:
                # Instead of Message there goes just Tx. For this particular test their attributes are compatible!
                if event := self.make_swap_start_event(tx, tx_hash, height, is_deposit=False):
                    yield event
            except Exception as e:
                self.logger.error(f'Could not parse Observed In TX ({tx}): {e!r}')

    def detect_swaps(self, b: BlockResult):
        deposits = b.find_tx_by_type(ThorTxMessage.MsgDeposit)
        deposit_swap_starts = list(self.handle_deposits(deposits, b.block_no))

        # they are based only on memo parsed (just intention, real swap quantity may differ)
        observed_in_txs = b.find_tx_by_type(ThorTxMessage.MsgObservedTxIn)
        observed_in_txs = list(self.handle_observed_txs(observed_in_txs, b.block_no))

        return deposit_swap_starts + observed_in_txs
