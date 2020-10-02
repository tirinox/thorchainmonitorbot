import asyncio
import logging
from typing import List

import aiohttp

from services.config import Config, DB
from services.fetch.price import get_prices_of, STABLE_COIN
from services.models.tx import StakeTx, StakePoolStats

TRANSACTION_URL = "https://chaosnet-midgard.bepswap.com/v1/txs?offset={offset}&limit={limit}&type=stake,unstake"


class StakeTxFetcher:
    SLEEP_PERIOD = 60
    MAX_TX_PER_ONE_TIME = 150
    TX_PER_BATCH = 50

    def __init__(self, cfg: Config, db: DB):
        self.cfg = cfg
        self.db = db
        self.stat_map = {}
        self.price_map = {}

    def tx_endpoint_url(self, offset=0, limit=10):
        return TRANSACTION_URL.format(offset=offset, limit=limit)

    @staticmethod
    def _parse_txs(j):
        for tx in j['txs']:
            if tx['status'] == 'Success':
                yield StakeTx.load_from_midgard(tx)

    async def _fetch_one_batch(self, session, page):
        url = self.tx_endpoint_url(page * self.TX_PER_BATCH, self.TX_PER_BATCH)
        logging.info(f"start fetching tx: {url}")
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
                logging.info(f'already counted: {tx} stopping')
                break
            new_txs.append(tx)

        return stopped, new_txs

    async def _fetch_txs(self):
        all_txs = []
        try:
            page = 0
            while True:
                txs = await self._fetch_one_batch(self.session, page)
                stopped, txs = await self._filter_new(txs)
                if not txs:
                    logging.info(f"no more tx: got {len(all_txs)}")
                    break

                all_txs += txs
                page += 1

                if stopped or len(all_txs) >= self.MAX_TX_PER_ONE_TIME or page > 10:
                    break
        except (ValueError, TypeError, IndexError, ZeroDivisionError, KeyError) as e:
            logging.error(e)
        finally:
            return all_txs

    async def _update_pools(self, txs):
        updated_stats = set()
        result_txs = []

        for tx in txs:
            tx: StakeTx
            price = self.price_map.get(tx.pool)
            stats: StakePoolStats = self.stat_map.get(tx.pool)
            if price and stats:
                full_rune = tx.full_rune_amount(price)
                stats.update(full_rune)
                updated_stats.add(tx.pool)
                result_txs.append(tx)

        logging.info(f'pool stats updated for {", ".join(updated_stats)}')

        for pool_name in updated_stats:
            await self.stat_map[pool_name].save(self.db)

        logging.info(f'new tx to analyze: {len(result_txs)}')

        return result_txs

    async def _load_stats(self, txs):
        pool_names = StakeTx.collect_pools(txs)
        pool_names.add(STABLE_COIN)  # don't forget BUSD, for total usd volume!
        self.price_map = await get_prices_of(self.session, pool_names)
        self.stat_map = {
            pool: (await StakePoolStats.get_from_db(pool, self.db)) for pool in pool_names
        }

    def filter_small_txs(self, txs, threshold_factor=5.0):
        for tx in txs:
            tx: StakeTx
            stats: StakePoolStats = self.stat_map.get(tx.pool)
            if stats is not None:
                if tx.full_rune >= stats.rune_avg_amt * threshold_factor:
                    yield tx

    async def tick(self):
        async with aiohttp.ClientSession() as self.session:
            txs = await self._fetch_txs()
            if not txs:
                return []

            await self._load_stats(txs)

            txs = await self._update_pools(txs)
            return txs

    async def mark_as_notified(self, txs: List[StakeTx]):
        await asyncio.gather(*[
            tx.set_notified(self.db) for tx in txs
        ])

    async def on_new_txs(self, txs, runes_per_dollar):
        ...

    async def run(self):
        await asyncio.sleep(3)
        while True:
            txs = await self.tick()
            if txs:
                runes_per_dollar = self.price_map.get(STABLE_COIN, 1)
                await self.on_new_txs(txs, runes_per_dollar)
                await self.mark_as_notified(txs)
            await asyncio.sleep(self.SLEEP_PERIOD)
