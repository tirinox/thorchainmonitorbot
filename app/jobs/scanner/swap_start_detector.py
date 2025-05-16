from typing import Optional, Iterable

from jobs.scanner.native_scan import BlockResult
from jobs.scanner.tx import NativeThorTx, ThorTxMessage, ThorObservedTx
from lib.constants import NATIVE_RUNE_SYMBOL, thor_to_float
from lib.depcont import DepContainer
from lib.logs import WithLogger
from lib.utils import safe_get
from models.asset import Asset, is_rune
from models.memo import ActionType
from models.memo import THORMemo
from models.s_swap import StreamingSwap, AlertSwapStart


class SwapStartDetector(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    def make_swap_start_event(self, msg: dict, tx_hash, height, is_deposit) -> Optional[AlertSwapStart]:
        """
        msg is a dict, either MsgDeposit.messages[i] or MsgObservedTxIn.messages[i].txs[j].tx
        """
        memo_str = msg.get('memo') or safe_get(msg, 'tx', 'memo')
        if memo_str is None:
            self.logger.error(f'No memo in swap tx: {msg}')
            return None
        memo = THORMemo.parse_memo(memo_str, no_raise=True)

        # Must be a swap!
        if not memo or memo.action != ActionType.SWAP:
            return None

        coins = msg.get('coins') or safe_get(msg, 'tx', 'coins')
        if not coins:
            self.logger.error(f'No coins in swap tx: {msg}')
            return None

        prices = self.deps.price_holder
        assert prices, 'PriceHolder is required!'
        assert prices.pool_info_map, 'PriceHolder must have non-empty pool_info_map!'

        if is_rune(memo.asset):
            out_asset_name = NATIVE_RUNE_SYMBOL
        else:
            out_asset_name = prices.pool_fuzzy_first(memo.asset, restore_type=True)
            if not out_asset_name:
                out_asset_name = memo.asset
                self.logger.error(f'{out_asset_name = }: asset not found in the pool list!')

        if not out_asset_name:
            self.logger.error(f'{memo.asset}: asset not found!')
            return None

        # get data
        amount = coins[0]['amount']
        in_amount = thor_to_float(amount)
        in_asset = Asset.from_string(coins[0]["asset"])
        from_address = msg.get('from_address', None) or msg.get('signer', '') or safe_get(msg, 'tx', 'from_address')

        if str(in_asset) == NATIVE_RUNE_SYMBOL:
            volume_usd = in_amount * prices.usd_per_rune
        else:
            in_pool_name = prices.pool_fuzzy_first(in_asset.native_pool_name)
            if not in_pool_name:
                self.logger.warning(f'{in_asset.native_pool_name}: pool if inbound asset not found!')
                return None

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
            volume_usd=volume_usd,
            block_height=height,
            memo=memo,
            memo_str=memo_str,  # original memo
        )

    def handle_deposits(self, txs: Iterable[NativeThorTx], height):
        results = []
        for tx in txs:
            for msg in tx.messages:
                try:
                    if event := self.make_swap_start_event(msg.attrs, tx.tx_hash, height, is_deposit=True):
                        results.append(event)
                except Exception as e:
                    self.logger.exception(f'Could not parse DepositTx TX ({tx.tx_hash}): {e!r}', exc_info=True)

        return results

    def handle_observed_txs(self, txs: Iterable[ThorObservedTx], height: int):
        for obs_tx in txs:
            try:
                # Instead of Message there goes just Tx. For this particular test their attributes are compatible!
                if obs_tx.is_inbound:
                    if event := self.make_swap_start_event(obs_tx.original, obs_tx.tx_id, height, is_deposit=False):
                        yield event
            except Exception as e:
                self.logger.error(f'Could not parse Observed In TX ({obs_tx}): {e!r}')

    def detect_swaps(self, b: BlockResult):
        deposits = b.find_tx_by_type(ThorTxMessage.MsgDeposit)
        deposit_swap_starts = list(self.handle_deposits(deposits, b.block_no))

        # they are based only on memo parsed (just intention, real swap quantity may differ)
        observed_in_txs = b.all_observed_txs
        observed_in_txs = list(self.handle_observed_txs(observed_in_txs, b.block_no))

        return deposit_swap_starts + observed_in_txs
