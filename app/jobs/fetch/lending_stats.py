from typing import List, Optional

from api.midgard.parser import get_parser_by_network_id
from api.midgard.urlgen import free_url_gen
from jobs.fetch.base import BaseFetcher
from jobs.volume_recorder import TxCountRecorder
from lib.constants import THOR_BASIS_POINT_MAX, RUNE_IDEAL_SUPPLY, thor_to_float
from lib.date_utils import parse_timespan_to_seconds, DAY, now_ts
from lib.depcont import DepContainer
from models.loans import LendingStats, BorrowerPool
from models.price import RuneMarketInfo
from models.vol_n import TxMetricType

MAX_AGE_TO_REPORT_ERROR = 3 * DAY

# https://github.com/HooriRn/thorchain_explorer_server
URL_VANAHEIMIX_BORROWERS = 'https://vanaheimex.com/api/borrowers'


class LendingStatsFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        period = parse_timespan_to_seconds(deps.cfg.lending.fetch_period)
        super().__init__(deps, period)
        self.midgard_parser = get_parser_by_network_id(deps.cfg.network_id)

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

    async def get_vanaheimix_borrowers(self):
        async with self.deps.session.get(URL_VANAHEIMIX_BORROWERS) as response:
            j = await response.json()
            if not isinstance(j, list):
                raise IOError(f'{URL_VANAHEIMIX_BORROWERS} returned no list')

            pools = [BorrowerPool.from_json(item) for item in j]
            return pools

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

        usd_per_rune = self.deps.price_holder.usd_per_rune

        for pool_name in enabled_pools:
            pool = price_holder.find_pool(pool_name)
            if not pool or not pool.original:
                self.logger.error(f'Pool {pool_name} not found. Failed to collect lending stats')
                continue

            pool_runes = thor_to_float(pool.original.balance_rune)

            # just convert collateral to Runes
            collateral_pool_in_rune = thor_to_float(pool.original.loan_collateral) * pool.original.runes_per_asset

            pool_stats.append(BorrowerPool(
                debt=thor_to_float(pool.original.loan_total),
                collateral=thor_to_float(pool.original.loan_collateral),
                available_rune=(pool_runes / total_balance_rune) * total_rune_protocol,
                fill=collateral_pool_in_rune / ((pool_runes / total_balance_rune) * total_rune_protocol),
                collateral_available=thor_to_float(pool.original.loan_collateral_remaining),
                pool=pool_name,
                borrowers_count=0,
                debt_in_rune=thor_to_float(pool.original.loan_collateral) / usd_per_rune,
                collateral_pool_in_rune=collateral_pool_in_rune,
                is_enabled=True,
            ))

        return stats

    async def _ensure_mimir(self):
        if not self.deps.mimir_const_holder.is_loaded:
            self.logger.warning('Mimir is not loaded. Force load it!')
            await self.deps.mimir_const_fetcher.run_once()
            if not self.deps.mimir_const_holder.is_loaded:
                self.logger.error('Mimir is not loaded. Failed to collect lending stats')
                self.deps.emergency.report(self.logger.name, 'Mimir is not loaded. Failed to collect lending stats')
                return False
        return True

    async def fetch(self) -> Optional[LendingStats]:
        if not await self._ensure_mimir():
            return

        lending_pools = await self.get_vanaheimix_borrowers()

        market_info = await self.deps.rune_market_fetcher.fetch()
        burnt_rune = market_info.supply_info.lending_burnt_rune if market_info and market_info.supply_info else 0.0

        tx_counter: TxCountRecorder = self.deps.tx_count_recorder
        tally_days_period = round(self.sleep_period / DAY)
        opened_loans, _ = await tx_counter.get_one_metric(TxMetricType.LOAN_OPEN, tally_days_period)
        closed_loans, _ = await tx_counter.get_one_metric(TxMetricType.LOAN_CLOSE, tally_days_period)
        lending_tx_count = opened_loans + closed_loans

        consts = self.deps.mimir_const_holder
        is_paused = bool(consts.get_constant('PAUSELOANS', 0))
        lending_lever = consts.get_constant('LENDINGLEVER', 3333) / THOR_BASIS_POINT_MAX
        loan_repayment_maturity_blk = consts.get_constant('LOANREPAYMENTMATURITY', 432000)
        min_cr = consts.get_constant('MINCR', 2000) / THOR_BASIS_POINT_MAX
        max_cr = consts.get_constant('MAXCR', 2000) / THOR_BASIS_POINT_MAX

        lending_stats = LendingStats(
            lending_tx_count=lending_tx_count,
            rune_burned_rune=burnt_rune,
            timestamp_day=now_ts(),
            pools=lending_pools,
            usd_per_rune=self.deps.price_holder.usd_per_rune,
            is_paused=is_paused,
            lending_lever=lending_lever,
            loan_repayment_maturity_blk=loan_repayment_maturity_blk,
            min_cr=min_cr,
            max_cr=max_cr,
        )
        return lending_stats

        # lending_stats = await self.get_fs_lending_stats()
        # if not lending_stats:
        #     self.logger.error(f'No lending stats')
        #     return
        #
        # # Check age
        # if lending_stats.data_age > MAX_AGE_TO_REPORT_ERROR:
        #     self.deps.emergency.report(self.name,
        #                                'Lending data is too old',
        #                                day=str(datetime.datetime.fromtimestamp(lending_stats.timestamp_day)))
        #     return
        #
        # # Amend burned rune
        #
        # # Enrich with lending caps
        # lending_stats = await self._enrich_with_caps(market_info, lending_stats)

        # return lending_stats
