from contextlib import suppress
from typing import NamedTuple, List

from services.lib.async_cache import AsyncTTL
from services.lib.constants import thor_to_float
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.price import LastPriceHolder
from services.models.savers import SaverVault, AlertSaverStats, SaversBank


class VNXSaversStats(NamedTuple):
    asset: str
    asset_depth: int
    asset_price: float
    earned: float
    earned_old: float
    filled: float
    savers_count: int
    savers_count_old: int
    saver_return: float
    saver_return_old: float
    savers_depth: int
    savers_depth_old: int
    synth_supply: int

    @classmethod
    def from_json(cls, j):
        new_j = j.get('savers')
        old_j = j.get('oldSavers')

        return cls(
            asset=new_j.get('asset', ''),
            asset_depth=int(new_j.get('assetDepth', 0.0)),
            asset_price=float(new_j.get('assetPriceUSD', 0.0)),

            filled=float(new_j.get('filled', 0.0)),

            earned=float(new_j.get('earned', 0.0)),
            earned_old=float(old_j.get('earned', 0.0)),

            savers_count=int(new_j.get('saversCount', 0)),
            savers_count_old=int(old_j.get('saversCount', 0)),

            saver_return=float(new_j.get('saversReturn', 0.0) or 0.0),
            saver_return_old=float(old_j.get('saversReturn', 0.0) or 0.0),

            savers_depth=int(new_j.get('saversDepth', 0.0)),
            savers_depth_old=int(old_j.get('saversDepth', 0.0)),

            synth_supply=int(new_j.get('synthSupply', 0.0)),
        )


class VNXSaversStatsFetcher(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    VNX_SAVERS_STATS_URL = 'https://vanaheimex.com/api/saversInfo'

    def convert(self, stats: VNXSaversStats, price_holder: LastPriceHolder, new=True):
        amount = thor_to_float(stats.savers_depth)
        amount_old = thor_to_float(stats.savers_depth_old)
        amount_usd = stats.asset_price * amount
        amount_usd_old = stats.asset_price * amount_old

        usd_per_rune = self.deps.price_holder.usd_per_rune

        max_synth_per_asset_ratio = self.deps.mimir_const_holder.get_max_synth_per_pool_depth()  # normally: 0.15

        pool = price_holder.find_pool(stats.asset)
        cap = pool.get_synth_cap_in_asset_float(max_synth_per_asset_ratio)
        rune_earned = thor_to_float(stats.earned) * stats.asset_price / usd_per_rune
        rune_earned_old = thor_to_float(stats.earned_old) * stats.asset_price / usd_per_rune

        return SaverVault(
            asset=stats.asset,
            number_of_savers=stats.savers_count if new else stats.savers_count_old,
            total_asset_saved=amount if new else amount_old,
            total_asset_saved_usd=amount_usd if new else amount_usd_old,
            apr=(stats.saver_return if new else stats.saver_return_old) * 100.0,
            asset_cap=cap,
            runes_earned=rune_earned if new else rune_earned_old,
            synth_supply=thor_to_float(stats.synth_supply),
        )

    async def load_real_yield_vanaheimex(self) -> List[VNXSaversStats]:
        url = self.VNX_SAVERS_STATS_URL
        self.logger.debug(f'Loading {url!r}...')
        async with self.deps.session.get(url) as resp:
            if resp.status != 200:
                self.logger.error(f'Response code for {url!r} is {resp.status}!')
                self.deps.emergency.report('VNXSaversStatsFetcher', 'Failed to load',
                                           status=resp.status, url=url)

            j = await resp.json()
            if not j:
                return []

            results = []
            for asset, sub_json in j.items():
                saver_vault = VNXSaversStats.from_json(sub_json)
                results.append(saver_vault)

            if not results:
                self.logger.error(f'No data received')
                self.deps.emergency.report('VNXSaversStatsFetcher', 'No data received', url=url)
            else:
                self.logger.info(f'Got {len(results)} rows.')

            return results

    @staticmethod
    def make_bank(vaults: List[SaverVault]):
        n = 0
        for v in vaults:
            n += v.number_of_savers
        return SaversBank(n, vaults)

    async def get_savers_event(self, *args) -> AlertSaverStats:
        vnx_vaults = await self.load_real_yield_vanaheimex()
        vaults = [self.convert(v, self.deps.price_holder) for v in vnx_vaults]
        curr_saver = self.make_bank(vaults)
        old_vaults = [self.convert(v, self.deps.price_holder, new=False) for v in vnx_vaults]
        prev_state = self.make_bank(old_vaults)
        return AlertSaverStats(prev_state, curr_saver, self.deps.price_holder)

    CACHE_TTL = 60

    @AsyncTTL(time_to_live=CACHE_TTL)
    async def get_savers_event_cached(self) -> AlertSaverStats:
        return await self.get_savers_event()

    async def on_data(self, sender, data):
        with suppress(Exception):
            vaults = await self.load_real_yield_vanaheimex()
            vaults = [self.convert(v, self.deps.price_holder) for v in vaults]
            bank = self.make_bank(vaults)
            await self.pass_data_to_listeners(bank)
