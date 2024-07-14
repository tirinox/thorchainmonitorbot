import datetime
from typing import List, Optional

from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.flipside.flipside import FlipSideConnector
from services.jobs.fetch.flipside.urls import URL_FS_BORROWERS_V3
from services.lib.constants import THOR_BASIS_POINT_MAX, RUNE_IDEAL_SUPPLY, thor_to_float
from services.lib.date_utils import parse_timespan_to_seconds, DAY
from services.lib.depcont import DepContainer
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import free_url_gen
from services.models.loans import LendingStats, PoolLendState
from services.models.price import RuneMarketInfo

MAX_AGE_TO_REPORT_ERROR = 3 * DAY


class LendingStatsFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        period = parse_timespan_to_seconds(deps.cfg.lending.fetch_period)
        super().__init__(deps, period)
        self.midgard_parser = get_parser_by_network_id(deps.cfg.network_id)
        self.fs = FlipSideConnector(deps.session, deps.cfg.flipside.api_key)

    async def get_borrower_list(self) -> List[str]:
        borrowers = await self.deps.midgard_connector.request(free_url_gen.url_borrowers())

        if not borrowers:
            self.logger.warning(f'No borrowers found')
            return []
        return borrowers

    @staticmethod
    async def amend_burned_rune(lending_stats: LendingStats, market_info):
        if not market_info or not market_info.supply_info:
            return lending_stats

        real_burned_rune = market_info.supply_info.lending_burnt_rune
        if real_burned_rune is not None:
            lending_stats = lending_stats._replace(rune_burned_rune=real_burned_rune)
        return lending_stats

    async def get_fs_lending_stats(self) -> Optional[LendingStats]:
        data = await self.fs.request(URL_FS_BORROWERS_V3)
        if data:
            lending_stats = LendingStats.from_fs_json(data)
            return lending_stats

    def get_total_rune_for_protocol(self, market_info: RuneMarketInfo) -> float:
        consts = self.deps.mimir_const_holder
        lever = consts.get_constant('LENDINGLEVER', 3333) / THOR_BASIS_POINT_MAX
        max_rune_supply = RUNE_IDEAL_SUPPLY
        current_rune_supply = market_info.supply_info.total
        total_rune_for_protocol = lever * (max_rune_supply - current_rune_supply)
        return total_rune_for_protocol

    def get_enabled_pools_for_lending(self):
        mimir = self.deps.mimir_const_holder
        if not mimir.all_entries:
            self.logger.error('No mimir entries found')

        price_holder = self.deps.price_holder
        if not price_holder.pool_info_map:
            self.logger.error('No pool info map found')

        for entry in mimir.all_entries:
            if (key := entry.name.upper()).startswith('LENDING-THOR-'):
                key_parts = key.split('-', maxsplit=2)
                pool_name = price_holder.pool_fuzzy_first(key_parts[2])
                if pool_name:
                    yield pool_name

    async def _enrich_with_caps(self, market_info: RuneMarketInfo, stats: LendingStats) -> LendingStats:
        pool_stats = stats.pools
        pool_stats.clear()

        enabled_pools = list(self.get_enabled_pools_for_lending())
        price_holder = self.deps.price_holder

        total_balance_rune = 0.0
        for pool_name in enabled_pools:
            pool = price_holder.find_pool(pool_name)
            if pool and pool.original:
                total_balance_rune += thor_to_float(pool.original.balance_rune)

        total_rune_protocol = self.get_total_rune_for_protocol(market_info)

        for pool_name in enabled_pools:
            pool = price_holder.find_pool(pool_name)
            if not pool or not pool.original:
                self.logger.error(f'Pool {pool_name} not found. Failed to collect lending stats')
                continue

            pool_runes = thor_to_float(pool.original.balance_rune)

            # just convert collateral to Runes
            collateral_pool_in_rune = thor_to_float(pool.original.loan_collateral) * pool.original.runes_per_asset

            pool_stats.append(PoolLendState(
                pool_name,
                collateral_amount=thor_to_float(pool.original.loan_collateral),
                available_rune=(pool_runes / total_balance_rune) * total_rune_protocol,
                fill_ratio=collateral_pool_in_rune / ((pool_runes / total_balance_rune) * total_rune_protocol),
                collateral_available=thor_to_float(pool.original.loan_collateral_remaining)
            ))

        return stats

    async def fetch(self) -> Optional[LendingStats]:
        # Load
        lending_stats = await self.get_fs_lending_stats()
        if not lending_stats:
            self.logger.error(f'No lending stats')
            return

        # Check age
        if lending_stats.data_age > MAX_AGE_TO_REPORT_ERROR:
            self.deps.emergency.report(self.name,
                                       'Lending data is too old',
                                       day=str(datetime.datetime.fromtimestamp(lending_stats.timestamp_day)))
            return

        # Amend burned rune
        market_info = await self.deps.rune_market_fetcher.get_rune_market_info()
        lending_stats = await self.amend_burned_rune(lending_stats, market_info)

        # Enrich with lending caps
        lending_stats = await self._enrich_with_caps(market_info, lending_stats)

        return lending_stats
