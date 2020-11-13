import asyncio
from typing import List

import aiohttp
from aiohttp import ClientSession

from services.config import Config
from services.db import DB
from services.fetch.base import BaseFetcher, INotified
from services.fetch.pool_price import BUSD_SYMBOL, PoolPriceFetcher
from services.models.pool_info import PoolInfo
from services.models.tx import StakeTx, StakePoolStats

TRANSACTION_URL = "https://chaosnet-midgard.bepswap.com/v1/txs?offset={offset}&limit={limit}&type=stake,unstake"


class StakeTxFetcher(BaseFetcher):
    MAX_PAGE_DEEP = 10

    def __init__(self, cfg: Config, db: DB, session: ClientSession, ppf: PoolPriceFetcher, delegate: INotified = None):
        super().__init__(cfg, db, session, sleep_period=60, delegate=delegate)

        self.pool_stat_map = {}
        self.pool_info_map = {}

        scfg = cfg.tx.stake_unstake
        self.avg_n = int(scfg.avg_n)
        self.ppf = ppf
        self.sleep_period = int(scfg.fetch_period)
        self.tx_per_batch = int(scfg.tx_per_batch)
        self.max_page_deep = int(scfg.max_page_deep)

        self.logger.info(f"cfg.tx.stake_unstake: {scfg}")

    @property
    def usd_per_rune(self):
        return self.pool_info_map.get(BUSD_SYMBOL, PoolInfo.dummy()).price

    async def fetch(self):
        async with aiohttp.ClientSession() as self.session:
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
            if tx['status'] == 'Success':
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
        stopped = False
        for tx in txs:
            tx: StakeTx
            if await tx.is_notified(self.db):
                stopped = True
                self.logger.info(f'already counted: {tx} stopping')
                break
            new_txs.append(tx)

        return stopped, new_txs

    async def _fetch_txs(self):
        all_txs = []
        page = 0
        while True:
            txs = await self._fetch_one_batch(self.session, page)
            stopped, txs = await self._filter_new(txs)
            if not txs:
                self.logger.info(f"no more tx: got {len(all_txs)}")
                break

            all_txs += txs
            page += 1

            if stopped or page > self.max_page_deep:
                break

        return all_txs

    async def _update_pools(self, txs):
        updated_stats = set()
        result_txs = []

        for tx in txs:
            tx: StakeTx
            price = self.pool_info_map.get(tx.pool, PoolInfo.dummy()).price
            stats: StakePoolStats = self.pool_stat_map.get(tx.pool)
            if price and stats:
                full_rune = tx.full_rune_amount(price)
                stats.update(full_rune, self.avg_n)
                updated_stats.add(tx.pool)
                result_txs.append(tx)

        self.logger.info(f'pool stats updated for {", ".join(updated_stats)}')

        for pool_name in updated_stats:
            pool_stat: StakePoolStats = self.pool_stat_map[pool_name]
            pool_info: PoolInfo = self.pool_info_map.get(pool_name)
            pool_stat.usd_depth = pool_info.usd_depth(self.usd_per_rune)
            await pool_stat.write_time_series(self.db)
            await pool_stat.save(self.db)

        self.logger.info(f'new tx to analyze: {len(result_txs)}')

        return result_txs

    async def _load_stats(self, txs):
        pool_names = StakeTx.collect_pools(txs)
        pool_names.add(BUSD_SYMBOL)  # don't forget BUSD, for total usd volume!
        self.pool_info_map = await self.ppf.get_current_pool_data_full()
        self.pool_stat_map = {
            pool: (await StakePoolStats.get_from_db(pool, self.db)) for pool in pool_names
        }

    async def _mark_as_notified(self, txs: List[StakeTx]):
        await asyncio.gather(*[
            tx.set_notified(self.db) for tx in txs
        ])
