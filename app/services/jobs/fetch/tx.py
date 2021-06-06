from aioredis import Redis
from typing import List

from tqdm import tqdm

from services.jobs.fetch.base import BaseFetcher
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import get_url_gen_by_network_id
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.models.tx import ThorTx


class TxFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        scfg = deps.cfg.tx.liquidity

        sleep_period = parse_timespan_to_seconds(scfg.fetch_period)
        super().__init__(deps, sleep_period=sleep_period)

        self.tx_per_batch = int(scfg.tx_per_batch)
        self.max_page_deep = int(scfg.max_page_deep)
        self.url_gen_midgard = get_url_gen_by_network_id(deps.cfg.network_id)
        self.tx_parser = get_parser_by_network_id(deps.cfg.network_id)
        self.progress_tracker: tqdm = None

        self.logger.info(f"cfg.tx.liquidity: {scfg}")

    async def fetch(self):
        await self.deps.db.get_redis()
        txs = await self._fetch_txs()
        self.logger.info(f'new tx to analyze: {len(txs)}')
        return txs

    # -----------------------

    def _update_progress(self, new_txs, total):
        if self.progress_tracker:
            if total and total > 0:
                self.progress_tracker.total = total
            self.progress_tracker.update(new_txs)

    async def fetch_all_tx(self, address=None, liquidity_change_only=False, max_pages=None) -> List[ThorTx]:
        page = 0
        txs = []
        types = self.url_gen_midgard.LIQUIDITY_TX_TYPES_STRING if liquidity_change_only else None
        while True:
            url = self.url_gen_midgard.url_for_tx(page * self.tx_per_batch, self.tx_per_batch,
                                                  types=types,
                                                  address=address)

            if not self.progress_tracker:
                self.logger.info(f"start fetching user's tx: {url}")

            async with self.deps.session.get(url) as resp:
                json = await resp.json()
                new_txs = self.tx_parser.parse_tx_response(json)

                self._update_progress(new_txs.tx_count, new_txs.total_count)

                txs += new_txs.txs
                if not new_txs.tx_count or new_txs.tx_count < self.tx_per_batch:
                    break
                page += 1

            if max_pages and page >= max_pages:
                self.logger.info(f'Max pages {max_pages} reached.')
                break
        self.logger.info(f'User {address = } has {len(txs)} tx ({liquidity_change_only = }).')
        return txs

    # -------

    async def _fetch_one_batch(self, session, page):
        url = self.url_gen_midgard.url_for_tx(page * self.tx_per_batch, self.tx_per_batch)
        self.logger.info(f"start fetching tx: {url}")
        async with session.get(url) as resp:
            json = await resp.json()
            return self.tx_parser.parse_tx_response(json)

    async def _fetch_txs(self):
        all_txs = []
        await self.deps.db.get_redis()
        for page in range(self.max_page_deep):
            results = await self._fetch_one_batch(self.deps.session, page)
            new_txs = []
            for tx in results.txs:
                if tx.is_success and not (await self.is_seen(tx.tx_hash)):
                    new_txs.append(tx)
            if not new_txs:
                self.logger.info(f"no more tx: got {len(all_txs)}")
                break
            all_txs += new_txs
        return all_txs

    KEY_LAST_SEEN_TX_HASH = 'tx:scanner:last_seen:hash'

    async def is_seen(self, tx_hash):
        if not tx_hash:
            return False
        r: Redis = self.deps.db.redis
        return await r.sismember(self.KEY_LAST_SEEN_TX_HASH, tx_hash)

    async def add_last_seen_tx_hashes(self, hashes):
        if hashes:
            r: Redis = await self.deps.db.get_redis()
            await r.sadd(self.KEY_LAST_SEEN_TX_HASH, *hashes)

    async def clear_all_seen_tx(self):
        r: Redis = await self.deps.db.get_redis()
        await r.delete(self.KEY_LAST_SEEN_TX_HASH)
