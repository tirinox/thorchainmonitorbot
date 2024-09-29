from typing import List

from jobs.fetch.base import BaseFetcher
from lib.constants import Chains, float_to_thor, thor_to_float, THOR_BLOCK_TIME, bp_to_float
from lib.date_utils import parse_timespan_to_seconds
from lib.depcont import DepContainer
from lib.utils import WithLogger
from models.asset import Asset, AssetRUNE
from models.s_swap import StreamingSwap


class StreamingSwapFechter(BaseFetcher, WithLogger):
    PATH = '/thorchain/swaps/streaming'

    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.streaming_swaps.fetch_period)
        super().__init__(deps, sleep_period)

    async def fetch(self) -> List[StreamingSwap]:
        # I've got to dig in the guts because aionode treats null response as a fail and retries
        client = self.deps.thor_connector._clients[0]  # Get the primary client
        resp = await client.request(self.PATH)
        if not isinstance(resp, list):
            return []

        swaps = [StreamingSwap.from_json(ss) for ss in resp]  # Load models
        return swaps



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

        result = await self.deps.thor_connector.query_raw(
            f'thorchain/quote/swap'
            f'?amount={amount_to_send}'
            f'&from_asset={from_asset!s}'
            f'&to_asset={to_asset!s}'
            f'&destination={destination_address}'
        )

        if err := result.get('error'):
            raise Exception(f'Error: "{err}"')

        expected_amount_out = thor_to_float(result.expected_amount_out)
        expected_amount_out_usd = expected_amount_out * asset_out_price_usd

        inbound_confirmation_seconds = result.get('inbound_confirmation_seconds', 0)
        outbound_delay_seconds = int(result["outbound_delay_blocks"]) * THOR_BLOCK_TIME
        estimated_swap_time = inbound_confirmation_seconds + outbound_delay_seconds

        slippage_bps = int(result['slippage_bps'])

        asset_depth = thor_to_float(in_pool.balance_asset)
        two_bps_depth = bp_to_float(2) * asset_depth

        full_swaps, reminder_swap = divmod(asset_depth, two_bps_depth)
        full_swaps = int(full_swaps)

        # to be continued...