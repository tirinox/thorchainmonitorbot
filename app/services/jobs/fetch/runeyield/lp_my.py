import asyncio
import json
from typing import List, Tuple, Dict, Optional

from aioredis import Redis

from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.jobs.fetch.runeyield import AsgardConsumerConnectorBase
from services.jobs.fetch.tx import TxFetcher
from services.lib.constants import THOR_DIVIDER_INV, STABLE_COIN_POOLS
from services.lib.depcont import DepContainer
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import MidgardURLGenBase
from services.lib.money import weighted_mean
from services.models.pool_info import PoolInfo, parse_thor_pools
from services.models.pool_member import PoolMemberDetails
from services.models.stake_info import StakePoolReport, CurrentLiquidity, FeeResponse
from services.models.tx import ThorTx, ThorTxType

HeightToAllPools = Dict[int, Dict[str, PoolInfo]]


class HomebrewLPConnector(AsgardConsumerConnectorBase):
    def __init__(self, deps: DepContainer, ppf: PoolPriceFetcher, url_gen: MidgardURLGenBase):
        super().__init__(deps, ppf, url_gen)
        self.tx_fetcher = TxFetcher(deps)
        self.parser = get_parser_by_network_id(deps.cfg.network_id)
        self.use_thor_consensus = True

    async def generate_yield_summary(self, address, pools: List[str]) -> Tuple[dict, List[StakePoolReport]]:
        user_txs = await self._get_user_tx_actions(address)

        historic_all_pool_states, current_pools_details = await asyncio.gather(
            self._fetch_historical_pool_states(user_txs),
            self._get_details_of_staked_pools(address, pools)
        )

        d = self.deps
        reports = []
        for pool_details in current_pools_details.values():
            this_pool_txs = [tx for tx in user_txs if tx.first_pool == pool_details.pool]
            liq = self._get_current_liquidity(this_pool_txs, pool_details, historic_all_pool_states)
            fees = await self._get_fee_report()
            usd_per_asset_start, usd_per_rune_start = self._get_earliest_prices(this_pool_txs, historic_all_pool_states)
            stake_report = StakePoolReport(
                d.price_holder.usd_per_asset(liq.pool),
                d.price_holder.usd_per_rune,
                usd_per_asset_start, usd_per_rune_start,
                liq, fees=fees,
                pool=d.price_holder.pool_info_map.get(liq.pool)
            )
            reports.append(stake_report)

        weekly_chars = {}
        return weekly_chars, reports

    async def generate_yield_report_single_pool(self, address, pool) -> StakePoolReport:
        # todo: idea: check date_last_added, if it is not changed - get user_txs from local cache

        user_txs = await self._get_user_tx_actions(address, pool)

        historic_all_pool_states, current_pools_details = await asyncio.gather(
            self._fetch_historical_pool_states(user_txs),
            self._get_details_of_staked_pools(address, pool)
        )

        # filter only 1 pool
        # historic_pool_state = {height: pools[pool] for height, pools in historic_all_pool_states.items()}
        current_pool_details: PoolMemberDetails = current_pools_details.get(pool)

        cur_liq = self._get_current_liquidity(user_txs, current_pool_details, historic_all_pool_states)

        # print(cur_liq)
        # print(current_pool_details)

        fees = await self._get_fee_report()
        usd_per_asset_start, usd_per_rune_start = self._get_earliest_prices(user_txs, historic_all_pool_states)

        d = self.deps
        stake_report = StakePoolReport(
            d.price_holder.usd_per_asset(cur_liq.pool),
            d.price_holder.usd_per_rune,
            usd_per_asset_start, usd_per_rune_start,
            cur_liq, fees=fees,
            pool=d.price_holder.pool_info_map.get(cur_liq.pool)
        )
        return stake_report

    async def get_my_pools(self, address) -> List[str]:
        url = self.url_gen.url_for_address_pool_membership(address)
        self.logger.info(f'get: {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            return self.parser.parse_pool_membership(j)

    # ----

    async def _get_user_tx_actions(self, address: str, pool_filter=None) -> List[ThorTx]:
        txs = await self.tx_fetcher.fetch_user_tx(address, liquidity_change_only=True)
        if pool_filter:
            txs = [tx for tx in txs if pool_filter in tx.pools]
        return txs

    async def _query_pools_cached(self, height) -> Dict[str, PoolInfo]:
        key = f"PoolInfo:height={height}"
        r: Redis = await self.deps.db.get_redis()
        cached_item = await r.get(key)
        if cached_item:
            raw_dict = json.loads(cached_item)
            pool_infos = {k: PoolInfo.from_dict(it) for k, it in raw_dict.items()}
            return pool_infos
        else:
            thor_pools = await self.deps.thor_connector.query_pools(height, consensus=self.use_thor_consensus)
            pool_infos = parse_thor_pools(thor_pools)
            j_pools = json.dumps({key: p.as_dict() for key, p in pool_infos.items()})
            await r.set(key, j_pools)
            return pool_infos

    async def purge_pool_height_cache(self):
        key_pattern = f"PoolInfo:height=*"
        r: Redis = await self.deps.db.get_redis()
        keys = await r.keys(key_pattern)
        if keys:
            await r.delete(*keys)

    async def _fetch_historical_pool_states(self, txs: List[ThorTx]) -> HeightToAllPools:
        heights = list(set(tx.height_int for tx in txs))
        thor_conn = self.deps.thor_connector

        # make sure, that connections are fresh, in order not to update it at all the height simultaneously
        await thor_conn._get_random_clients()

        tasks = [self._query_pools_cached(h) for h in heights]
        pool_states = await asyncio.gather(*tasks)
        return dict(zip(heights, pool_states))

    async def _get_details_of_staked_pools(self, address, pools) -> Dict[str, PoolMemberDetails]:
        url = self.url_gen.url_details_of_pools(address, pools)
        self.logger.info(f'get: {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            if 'error' in j:
                raise FileNotFoundError(j['error'])
            pool_array = self.parser.parse_pool_member_details(j, address)
            return {p.pool: p for p in pool_array}

    def _get_current_liquidity(self, txs: List[ThorTx],
                               pool_details: PoolMemberDetails,
                               pool_historic: HeightToAllPools) -> CurrentLiquidity:
        first_state_date, last_stake_date = 0, 0
        total_added_rune, total_withdrawn_rune = 0.0, 0.0
        total_added_usd, total_withdrawn_usd = 0.0, 0.0
        total_added_asset, total_withdrawn_asset = 0.0, 0.0
        fee_earn_usd = 0.0

        for tx in txs:
            tx_timestamp = tx.date_timestamp
            first_state_date = min(first_state_date, tx_timestamp) if first_state_date else tx_timestamp
            last_stake_date = max(last_stake_date, tx_timestamp) if last_stake_date else tx_timestamp

            pools_info: Dict[str, PoolInfo] = pool_historic[tx.height_int]
            this_asset_pool_info = pools_info.get(pool_details.pool)

            usd_per_rune = self._calculate_weighted_rune_price_in_usd(pools_info)

            if tx.type == ThorTxType.TYPE_ADD_LIQUIDITY:
                runes = tx.sum_of_rune(in_only=True)
                assets = tx.sum_of_asset(pool_details.pool, in_only=True)

                total_this_runes = runes + this_asset_pool_info.runes_per_asset * assets

                total_added_rune += total_this_runes
                total_added_usd += total_this_runes * usd_per_rune
                total_added_asset += assets + this_asset_pool_info.asset_per_rune * runes
            else:
                runes = tx.sum_of_rune(out_only=True)
                assets = tx.sum_of_asset(pool_details.pool, out_only=True)

                total_this_runes = runes + this_asset_pool_info.runes_per_asset * assets

                total_withdrawn_rune += total_this_runes
                total_withdrawn_usd += total_this_runes * usd_per_rune
                total_withdrawn_asset += assets + this_asset_pool_info.asset_per_rune * runes

        m = THOR_DIVIDER_INV

        results = CurrentLiquidity(
            pool=pool_details.pool,
            rune_stake=pool_details.rune_added * m,
            asset_stake=pool_details.asset_added * m,
            pool_units=pool_details.liquidity_units,
            asset_withdrawn=pool_details.asset_withdrawn * m,
            rune_withdrawn=pool_details.rune_withdrawn * m,
            total_staked_asset=total_added_asset,
            total_staked_rune=total_added_rune,
            total_staked_usd=total_added_usd,
            total_unstaked_asset=total_withdrawn_asset,
            total_unstaked_rune=total_withdrawn_rune,
            total_unstaked_usd=total_withdrawn_usd,
            first_stake_ts=int(first_state_date),
            last_stake_ts=int(last_stake_date),
            fee_earn_usd=fee_earn_usd,
        )
        return results

    @staticmethod
    def _calculate_weighted_rune_price_in_usd(pool_map: Dict[str, PoolInfo]) -> Optional[float]:
        prices, weights = [], []
        for stable_symbol in STABLE_COIN_POOLS:
            pool_info = pool_map.get(stable_symbol)
            if pool_info and pool_info.balance_rune > 0 and pool_info.asset_per_rune > 0:
                prices.append(pool_info.asset_per_rune)
                weights.append(pool_info.balance_rune)

        if prices:
            return weighted_mean(prices, weights)

    def _get_earliest_prices(self, txs: List[ThorTx], pool_historic: HeightToAllPools) -> Tuple[
        Optional[float], Optional[float]]:
        if not txs:
            return None, None

        earliest_tx = txs[0]
        for tx in txs[1:]:
            if tx.height_int < earliest_tx.height_int:
                earliest_tx = tx

        earliest_pools = pool_historic.get(earliest_tx.height_int)
        usd_per_rune = self._calculate_weighted_rune_price_in_usd(earliest_pools)
        this_pool = earliest_pools.get(earliest_tx.first_pool)
        rune_per_asset = this_pool.runes_per_asset
        usd_per_asset = usd_per_rune * rune_per_asset

        return usd_per_asset, usd_per_rune

    async def _get_fee_report(self):
        return FeeResponse()
