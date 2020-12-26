import asyncio
from typing import List

from services.fetch.base import BaseFetcher
from services.lib.datetime import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.models.pool_info import PoolInfo
from services.models.time_series import BUSD_SYMBOL
from services.models.tx import StakeTx, StakePoolStats

TRANSACTION_URL = "https://chaosnet-midgard.bepswap.com/v1/txs?offset={offset}&limit={limit}&type=stake,unstake"


class StakeTxFetcher(BaseFetcher):
    MAX_PAGE_DEEP = 10

    def __init__(self, deps: DepContainer):
        super().__init__(deps, sleep_period=60)

        self.pool_stat_map = {}
        self.pool_info_map = {}

        scfg = deps.cfg.tx.stake_unstake

        self.sleep_period = parse_timespan_to_seconds(scfg.fetch_period)
        self.tx_per_batch = int(scfg.tx_per_batch)
        self.max_page_deep = int(scfg.max_page_deep)

        self.logger.info(f"cfg.tx.stake_unstake: {scfg}")

    async def fetch(self):
        await self.deps.db.get_redis()

        txs = await self._fetch_txs()
        if not txs:
            return []

        await self._load_stats(txs)

        txs = await self._update_pools(txs)
        if txs:
            await self._mark_as_notified(txs)
        return txs

    # -------

    @staticmethod
    def tx_endpoint_url(offset=0, limit=10):
        return TRANSACTION_URL.format(offset=offset, limit=limit)

    @staticmethod
    def _parse_txs(j):
        for tx in j['txs']:
            if str(tx['status']).lower() == 'success':
                yield StakeTx.load_from_midgard(tx)

    async def _fetch_one_batch(self, session, page):
        url = self.tx_endpoint_url(page * self.tx_per_batch, self.tx_per_batch)
        self.logger.info(f"start fetching tx: {url}")
        async with session.get(url) as resp:
            json = await resp.json()
            txs = self._parse_txs(json)
            return list(txs)

    async def _filter_new(self, txs):
        new_txs = []
        for tx in txs:
            tx: StakeTx
            if not (await tx.is_notified(self.deps.db)):
                new_txs.append(tx)
        return new_txs

    async def _fetch_txs(self):
        all_txs = []
        page = 0
        while page < self.max_page_deep:
            txs = await self._fetch_one_batch(self.deps.session, page)
            txs = await self._filter_new(txs)
            if not txs:
                self.logger.info(f"no more tx: got {len(all_txs)}")
                break

            all_txs += txs
            page += 1

        return all_txs

    async def _update_pools(self, txs):
        updated_stats = set()
        result_txs = []

        for tx in txs:
            tx: StakeTx
            price = self.pool_info_map.get(tx.pool, PoolInfo.dummy()).price
            stats: StakePoolStats = self.pool_stat_map.get(tx.pool)
            if price and stats:
                full_rune = tx.calc_full_rune_amount(price)
                stats.update(full_rune, 100)
                updated_stats.add(tx.pool)
                result_txs.append(tx)

        self.logger.info(f'pool stats updated for {", ".join(updated_stats)}')

        for pool_name in updated_stats:
            pool_stat: StakePoolStats = self.pool_stat_map[pool_name]
            pool_info: PoolInfo = self.pool_info_map.get(pool_name)
            pool_stat.usd_depth = pool_info.usd_depth(self.deps.price_holder.usd_per_rune)
            await pool_stat.write_time_series(self.deps.db)
            await pool_stat.save(self.deps.db)

        self.logger.info(f'new tx to analyze: {len(result_txs)}')

        return result_txs

    async def _load_stats(self, txs):
        self.pool_info_map = self.deps.price_holder.pool_info_map
        if not self.pool_info_map:
            raise LookupError("pool_info_map is not loaded into the price holder!")

        pool_names = StakeTx.collect_pools(txs)
        pool_names.add(BUSD_SYMBOL)  # don't forget BUSD, for total usd volume!
        self.pool_stat_map = {
            pool: (await StakePoolStats.get_from_db(pool, self.deps.db)) for pool in pool_names
        }

    async def _mark_as_notified(self, txs: List[StakeTx]):
        await asyncio.gather(*[
            tx.set_notified(self.deps.db) for tx in txs
        ])
