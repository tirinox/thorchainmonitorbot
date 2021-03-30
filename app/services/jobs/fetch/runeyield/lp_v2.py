from services.jobs.fetch.runeyield.base import AsgardConsumerConnectorBase
from services.models.stake_info import CurrentLiquidity, StakePoolReport


# MULTI-chain

# https://mctn.vercel.app/dashboard?thor=tthor1zzwlsaq84sxuyn8zt3fz5vredaycvgm7n8gs6e  multi-chain
# FEES:
# https://multichain-asgard-consumer-api.vercel.app/api/v2/member/fee?address=tthor1zzwlsaq84sxuyn8zt3fz5vredaycvgm7n8gs6e|tb1qsasla0n6rjgwr6s4pa8jrqmvzzr0vfugulyyf0&pool=BTC.BTC
# thor address vs on-chain address:
# https://multichain-asgard-consumer-api.vercel.app/api/v2/member/pooladdress?address=tthor1zzwlsaq84sxuyn8zt3fz5vredaycvgm7n8gs6e
# POOL list of address:
# https://multichain-asgard-consumer-api.vercel.app/api/v2/member/poollist?address=tthor1zzwlsaq84sxuyn8zt3fz5vredaycvgm7n8gs6e&isDev
# Midgard pool info https://testnet.midgard.thorchain.info/v2/pool/BTC.BTC
# Weekly: not yet
# https://testnet.midgard.thorchain.info/v2/member/tthor1zzwlsaq84sxuyn8zt3fz5vredaycvgm7n8gs6e


class AsgardConsumerConnectorV2(AsgardConsumerConnectorBase):
    """
        Multichain Testnet/Chaosnet and Midgard V2 and app.runeyield.info connector
    """

    async def get_my_pools(self, address):
        url = self.url_gen.url_for_address_pool_membership(address)
        self.logger.info(f'get {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            try:
                my_pools = j.get('pools', [])
                return [p['pool'] for p in my_pools if 'pool' in p]
            except KeyError:
                return []

    async def _fetch_one_pool_liquidity_info(self, address, pool):
        raise NotImplementedError

    async def _generate_yield_report(self, liq: CurrentLiquidity) -> StakePoolReport:
        raise NotImplementedError

    async def _fetch_all_pool_liquidity_info(self, address, my_pools=None) -> dict:
        raise NotImplementedError

    async def _fetch_all_pools_weekly_charts(self, address, pools):
        raise NotImplementedError
