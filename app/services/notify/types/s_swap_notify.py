from services.lib.config import SubConfig
from services.lib.constants import Chains, float_to_thor
from services.lib.depcont import DepContainer
from services.lib.money import DepthCurve, Asset, AssetRUNE
from services.lib.utils import WithLogger
from services.models.tx import ThorTx
from services.notify.types.tx_notify import SwapTxNotifier


class StreamingSwapQuote(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.mock_addresses = {
            Chains.BTC: 'bc1qdvxpt06ulfk5gm5p52wa4mrt6e887wkmvc4xxw',
            Chains.ETH: '0x4E71F9debEC9117F1FACc7eeB490758AF45806A7',
            Chains.BNB: 'bnb1d8qn6p6vr6mjl2yf6x3xsen9z33jyhkt5tnlkp',
            Chains.BCH: 'pqvm5jv4zhy38dkzrx0md73c3sujhkmg4yhlmhhmfm',
            Chains.LTC: 'ltc1qzvcgmntglcuv4smv3lzj6k8szcvsrmvk0phrr9wfq8w493r096ssm2fgsw',
            Chains.AVAX: '0x66153cf0e164bc9bdae88fb36fc5b92dc63a79d6',
            Chains.BSC: '0x66153cf0e164bc9bdae88fb36fc5b92dc63a79d6',
            Chains.ATOM: 'cosmos1rdly788mpmwvemd5yr8wu0499zs4v4qnaptum4',
            Chains.DOGE: 'DLmW4rFuPqR3cUyqJiBqjho2CtHMC12bFt',
        }
        self.rune = AssetRUNE

    async def fetch_quotes(self, amount: float, from_asset: str, to_asset: str):
        if from_asset == to_asset:
            raise ValueError('From-asset and to-asset must be different.')

        from_asset = Asset.from_string(from_asset)
        to_asset = Asset.from_string(to_asset)
        destination_address = self.mock_addresses[from_asset.chain]

        amount_to_send = float_to_thor(amount)

        price_holder = self.deps.price_holder

        in_pool = price_holder.find_pool(from_asset)
        out_pool = price_holder.find_pool(to_asset)

        if from_asset == AssetRUNE:
            asset_in_price_usd = price_holder.usd_per_rune
        else:
            asset_in_price_usd = in_pool.usd_per_asset

        if to_asset == AssetRUNE:
            asset_out_price_usd = price_holder.usd_per_rune
        else:
            asset_out_price_usd = out_pool.usd_per_asset

        estimated_value_usd = amount * asset_in_price_usd

        await self.deps.thor_connector.query_raw(
            f'thorchain/quote/swap'
            f'?amount={amount_to_send}'
            f'&from_asset={from_asset!s}'
            f'&to_asset={to_asset!s}'
            f'&destination={destination_address}'
        )


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
