import time

from aiohttp import ContentTypeError
from aioredis import Redis
from typing import List, Optional

from tqdm import tqdm

from services.jobs.fetch.base import BaseFetcher
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import get_url_gen_by_network_id
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.models.tx import ThorTx, ThorTxExtended


class TxFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        s_cfg = deps.cfg.tx
        self.logger.info(f"cfg.tx: {s_cfg}")

        sleep_period = parse_timespan_to_seconds(s_cfg.fetch_period)
        super().__init__(deps, sleep_period=sleep_period)

        self.tx_per_batch = int(s_cfg.tx_per_batch)
        self.max_page_deep = int(s_cfg.max_page_deep)
        self.max_age_sec = parse_timespan_to_seconds(s_cfg.max_age)

        self.url_gen_midgard = get_url_gen_by_network_id(deps.cfg.network_id)
        self.tx_parser = get_parser_by_network_id(deps.cfg.network_id)

        self.progress_tracker: Optional[tqdm] = None

    async def fetch(self):
        await self.deps.db.get_redis()
        txs = await self._fetch_unseen_txs()
        self.logger.info(f'New tx to analyze: {len(txs)}')
        return txs

    async def post_action(self, txs: List[ThorTxExtended]):
        hashes = [t.tx.tx_hash for t in txs]
        await self.mark_tx_hashes_as_seen(hashes)

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
        try:
            async with session.get(url) as resp:
                json = await resp.json()
                return self.tx_parser.parse_tx_response(json)
        except ContentTypeError:
            return None

    async def _fetch_unseen_txs(self):
        all_txs = []
        await self.deps.db.get_redis()
        for page in range(self.max_page_deep):
            results = await self._fetch_one_batch(self.deps.session, page)

            if results is None:
                continue

            new_txs = results.txs
            new_txs = [tx for tx in new_txs if tx.is_success]  # filter success
            new_txs = list(self._filter_by_age(new_txs))  # filter out old TXs

            # filter out seen TXs
            for tx in results.txs:
                is_seen = await self.is_seen(tx.tx_hash)
                if not is_seen:
                    new_txs.append(tx)

            if not results.txs:
                self.logger.info(f"no more tx: got {len(all_txs)}")
                break

            all_txs += new_txs
        return all_txs

    def _filter_by_age(self, txs: List[ThorTx]):
        now = int(time.time())
        for tx in txs:
            if tx.date_timestamp > now - self.max_age_sec:
                yield tx

    KEY_LAST_SEEN_TX_HASH = 'tx:scanner:last_seen:hash'

    async def is_seen(self, tx_hash):
        if not tx_hash:
            return False
        r: Redis = self.deps.db.redis
        return await r.sismember(self.KEY_LAST_SEEN_TX_HASH, tx_hash)

    async def mark_tx_hashes_as_seen(self, hashes):
        if hashes:
            r: Redis = await self.deps.db.get_redis()
            await r.sadd(self.KEY_LAST_SEEN_TX_HASH, *hashes)

    async def clear_all_seen_tx(self):
        r: Redis = await self.deps.db.get_redis()
        await r.delete(self.KEY_LAST_SEEN_TX_HASH)
