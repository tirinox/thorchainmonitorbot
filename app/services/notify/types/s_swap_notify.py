from services.lib.config import SubConfig
from services.lib.depcont import DepContainer
from services.lib.money import DepthCurve
from services.models.tx import ThorTx
from services.notify.types.tx_notify import SwapTxNotifier


"""
Template:

----
🔁 Streaming swap started
43344 USD -> RUNE [10 swaps every 15 block, about 15 minutes to ago]
Expected rate 1.45 USDC/RUNE 

---------------------

🔁 Streaming swap finished
👤[d.thor]: 25.9 $ETH → ⚡ → 28.9 $ETH ($53.6K)
⏱️ Time elapsed: 25 minutes
Success: 35% (35/100)
Liq. fee: $3.0K❗
Est. Savings vs CEX: $96,54   
https://viewblock.io/thorchain/tx/49D3B64A87ACE299AECB75E64D40F8D4754CB41A5EB79FB02C991DB1B6657E7F
 
"""

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
