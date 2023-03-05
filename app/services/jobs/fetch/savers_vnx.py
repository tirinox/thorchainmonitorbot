import asyncio
from typing import NamedTuple, List

from services.lib.async_cache import AsyncTTL
from services.lib.constants import thor_to_float
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.price import LastPriceHolder
from services.models.savers import SaverVault, EventSaverStats, SaversBank


class VNXSaversStats(NamedTuple):
    asset: str
    asset_depth: int
    asset_price: float
    delta_earned: float
    earned: float
    filled: float
    savers_count: int
    saver_return: float
    savers_depth: int
    synth_supply: int

    @classmethod
    def from_json(cls, j):
        return cls(
            asset=j.get('asset'),
            asset_depth=int(j.get('assetDepth')),
            asset_price=float(j.get('assetPrice')),
            delta_earned=float(j.get('deltaEarned')),
            earned=float(j.get('earned')),
            filled=float(j.get('filled')),
            savers_count=int(j.get('saversCount')),
            saver_return=float(j.get('saverReturn')),
            savers_depth=int(j.get('saversDepth')),
            synth_supply=int(j.get('synthSupply')),
        )


class VNXSaversStatsFetcher(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    VNX_SAVERS_STATS_URL = 'https://vanaheimex.com/api/saversExtraData'
    VNX_SAVERS_STATS_PREV_URL = 'https://vanaheimex.com/api/oldSaversExtraData'

    def convert(self, stats: VNXSaversStats, price_holder: LastPriceHolder):
        amount = thor_to_float(stats.savers_depth)
        usd_per_rune = self.deps.price_holder.usd_per_rune

        max_synth_per_asset_ratio = self.deps.mimir_const_holder.get_max_synth_per_pool_depth()  # normally: 0.15

        pool = price_holder.find_pool(stats.asset)
        cap = pool.get_synth_cap_in_asset_float(max_synth_per_asset_ratio)
        rune_earned = thor_to_float(stats.earned) * stats.asset_price / usd_per_rune

        return SaverVault(
            asset=stats.asset,
            number_of_savers=stats.savers_count,
            total_asset_saved=amount,
            total_asset_saved_usd=stats.asset_price * amount,
            apr=stats.saver_return * 100.0,
            asset_cap=cap,
            runes_earned=rune_earned,
            synth_supply=thor_to_float(stats.synth_supply),
        )

    async def load_real_yield_vanaheimex(self, old=False) -> List[SaverVault]:
        url = self.VNX_SAVERS_STATS_PREV_URL if old else self.VNX_SAVERS_STATS_URL
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            results = []
            for asset, sub_json in j.items():
                saver_vault = VNXSaversStats.from_json(sub_json)
                saver_vault = self.convert(saver_vault, self.deps.price_holder)
                results.append(saver_vault)
            return results

    @staticmethod
    def make_bank(vaults: List[SaverVault]):
        n = 0
        for v in vaults:
            n += v.number_of_savers
        return SaversBank(n, vaults)

    async def get_savers_event(self, *args) -> EventSaverStats:
        savers_stats_new, savers_stats_old = await asyncio.gather(
            self.load_real_yield_vanaheimex(),
            self.load_real_yield_vanaheimex(old=True)
        )

        price_holder = self.deps.price_holder

        curr_saver = self.make_bank(savers_stats_new)
        prev_saver = self.make_bank(savers_stats_old)

        return EventSaverStats(
            prev_saver, curr_saver, price_holder
        )

    CACHE_TTL = 60

    @AsyncTTL(time_to_live=CACHE_TTL)
    async def get_savers_event_cached(self) -> EventSaverStats:
        return await self.get_savers_event()

    async def on_data(self, sender, data):
        vaults = await self.load_real_yield_vanaheimex()
        bank = self.make_bank(vaults)
        await self.pass_data_to_listeners(bank)
