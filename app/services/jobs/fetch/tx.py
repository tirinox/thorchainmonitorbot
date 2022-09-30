import asyncio
from typing import List, Optional

from aiohttp import ContentTypeError
from aioredis import Redis
from tqdm import tqdm

from services.jobs.affiliate_merge import AffiliateTXMerger
from services.jobs.fetch.base import BaseFetcher
from services.lib.date_utils import parse_timespan_to_seconds, now_ts
from services.lib.depcont import DepContainer
from services.lib.midgard.parser import get_parser_by_network_id, TxParseResult
from services.lib.midgard.urlgen import free_url_gen
from services.models.tx import ThorTx, ThorTxExtended


class TxFetcher(BaseFetcher):
    PAGE_IN_GROUP = 3

    def __init__(self, deps: DepContainer):
        s_cfg = deps.cfg.tx
        sleep_period = parse_timespan_to_seconds(s_cfg.fetch_period)
        super().__init__(deps, sleep_period=sleep_period)

        self.tx_per_batch = int(s_cfg.tx_per_batch)
        self.max_page_deep = int(s_cfg.max_page_deep)
        self.max_age_sec = parse_timespan_to_seconds(s_cfg.max_age)
        self.announce_pending_after_blocks = int(s_cfg.announce_pending_after_blocks)

        self.tx_parser = get_parser_by_network_id(deps.cfg.network_id)
        self.tx_merger = AffiliateTXMerger()

        self.progress_tracker: Optional[tqdm] = None

    async def fetch(self):
        await self.deps.db.get_redis()
        txs = await self._fetch_unseen_txs()
        if txs:
            self.logger.info(f'New tx to analyze: {len(txs)}')
        return txs

    async def post_action(self, txs: List[ThorTxExtended]):
        hashes = [self.get_seen_hash(t) for t in txs]
        await self.mark_tx_hashes_as_seen(hashes)

    # -----------------------

    def _update_progress(self, new_txs, total):
        if self.progress_tracker:
            if total and total > 0:
                self.progress_tracker.total = total
            self.progress_tracker.update(new_txs)

    async def _fetch_all_tx_of_type(self,
                                    address=None,
                                    tx_type=None,
                                    max_pages=None) -> List[ThorTx]:
        page = 0
        txs = []

        while True:
            q_path = free_url_gen.url_for_tx(page * self.tx_per_batch, self.tx_per_batch,
                                             tx_type=tx_type,
                                             address=address)

            if not self.progress_tracker:
                self.logger.info(f"start fetching user's tx: {q_path}")

            j = await self.deps.midgard_connector.request_random_midgard(q_path)
            new_txs = self.tx_parser.parse_tx_response(j)

            self._update_progress(new_txs.tx_count, new_txs.total_count)

            txs += new_txs.txs
            if not new_txs.tx_count or new_txs.tx_count < self.tx_per_batch:
                break
            page += 1

            if max_pages and page >= max_pages:
                self.logger.info(f'Max pages {max_pages} reached.')
                break

        return txs

    async def fetch_all_tx(self, address=None, liquidity_change_only=False, max_pages=None) -> List[ThorTx]:
        tx_types = free_url_gen.LIQUIDITY_TX_TYPES if liquidity_change_only else [None]

        txs = []
        for tx_type in tx_types:
            this_type_txs = await self._fetch_all_tx_of_type(address, tx_type, max_pages)
            txs.extend(this_type_txs)

        txs.sort(key=lambda tx: tx.height_int)
        self.logger.info(f'User {address = } has {len(txs)} tx ({liquidity_change_only = }).')
        return txs

    # -------

    async def _fetch_one_batch(self, page) -> Optional[TxParseResult]:
        q_path = free_url_gen.url_for_tx(page * self.tx_per_batch, self.tx_per_batch)

        try:
            j = await self.deps.midgard_connector.request_random_midgard(q_path)
            return self.tx_parser.parse_tx_response(j)
        except (ContentTypeError, AttributeError):
            return None

    async def _fetch_one_batch_tries(self, page, tries) -> Optional[TxParseResult]:
        for _ in range(tries):
            data = await self._fetch_one_batch(page)
            if data:
                return data
            else:
                self.logger.warning('retry?')
        self.logger.warning('gave up!')

    async def _fetch_unseen_txs(self):
        all_txs = []

        top_block_height = 0

        futures = [
            self._fetch_one_batch_tries(page, tries=2) for page in range(self.max_page_deep)
        ]

        pending_txs = []

        for future in asyncio.as_completed(futures):
            results = await future

            # estimate "top_block_height"
            if results:
                top_block_height = max(top_block_height, max(tx.height_int for tx in results.txs))

            # filter out old really TXs
            txs = list(self._filter_by_age(results.txs))

            # filter success
            selected_txs = [tx for tx in txs if tx.is_success]

            # tx which are in pending state for quite a long time deserve to be announced with a corresponding mark
            block_height_threshold = top_block_height - self.announce_pending_after_blocks
            this_batch_pending = [tx for tx in txs if tx.is_pending]
            pending_old_txs = [tx for tx in this_batch_pending if tx.height_int < block_height_threshold]
            if pending_old_txs:
                self.logger.info(f'Pending old TXs are accounted too: {len(pending_old_txs)}.')
                selected_txs += pending_old_txs

            pending_txs += this_batch_pending
            for tx in this_batch_pending:
                h = top_block_height - tx.height_int
                print(f'{tx.tx_hash}: {h} blocks age')

            # filter out TXs that have been seen already
            unseen_new_txs = []
            for tx in selected_txs:
                is_seen = await self.is_seen(self.get_seen_hash(tx))

                if not is_seen:
                    unseen_new_txs.append(tx)

            if not results.txs:
                self.logger.info(f"no more tx: got {len(all_txs)}")
                break

            all_txs += unseen_new_txs

        all_txs = self.tx_merger.merge_affiliate_txs(all_txs)

        # fixme: remove
        self.logger.info(f'Pending: {len(pending_txs)}')

        return all_txs

    @staticmethod
    def get_seen_hash(tx: ThorTx):
        return tx.tx_hash

    def _filter_by_age(self, txs: List[ThorTx]):
        # do nothing
        if self.max_age_sec == 0:
            return txs

        now = int(now_ts())
        for tx in txs:
            if tx.date_timestamp > now - self.max_age_sec:
                yield tx

    KEY_LAST_SEEN_TX_HASH = 'tx:scanner:last_seen:hash'

    async def is_seen(self, tx_hash):
        if not tx_hash:
            return True
        r: Redis = self.deps.db.redis
        return await r.sismember(self.KEY_LAST_SEEN_TX_HASH, tx_hash)

    async def mark_tx_hashes_as_seen(self, hashes):
        if hashes:
            r: Redis = await self.deps.db.get_redis()
            await r.sadd(self.KEY_LAST_SEEN_TX_HASH, *hashes)

    async def clear_all_seen_tx(self):
        r: Redis = await self.deps.db.get_redis()
        await r.delete(self.KEY_LAST_SEEN_TX_HASH)
