from services.lib.config import SubConfig
from services.lib.depcont import DepContainer
from services.lib.money import DepthCurve
from services.models.tx import ThorTx
from services.notify.types.tx_notify import SwapTxNotifier


class StreamingSwapTxNotifier(SwapTxNotifier):
    def __init__(self, deps: DepContainer, params: SubConfig, curve: DepthCurve):
        super().__init__(deps, params, curve)

        # todo: tune

    def is_tx_suitable(self, tx: ThorTx, min_rune_volume, usd_per_rune, curve_mult=None):
        return False
        # todo: filter
        # affiliate_fee_rune = tx.meta_swap.affiliate_fee * tx.full_rune
        #
        # if affiliate_fee_rune >= self.aff_fee_min_usd / usd_per_rune:
        #     return True
        #
        # if tx.dex_aggregator_used and tx.full_rune >= self.dex_min_usd / usd_per_rune:
        #     return True
        #
        # return super().is_tx_suitable(tx, min_rune_volume, usd_per_rune, curve_mult)
