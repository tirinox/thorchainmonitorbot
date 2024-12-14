from typing import List, Optional

from aiohttp import ContentTypeError
from tqdm import tqdm

from api.midgard.parser import get_parser_by_network_id, TxParseResult
from api.midgard.urlgen import free_url_gen
from jobs.affiliate_merge import AffiliateTXMerger
from jobs.fetch.base import BaseFetcher
from lib.date_utils import parse_timespan_to_seconds, now_ts
from lib.depcont import DepContainer
from models.tx import ThorAction
from notify.dup_stop import TxDeduplicator


class TxFetcher(BaseFetcher):
    RETRY_COUNT = 3

    def __init__(self, deps: DepContainer, tx_types=None, only_asset=None):
        s_cfg = deps.cfg.tx
        sleep_period = parse_timespan_to_seconds(s_cfg.fetch_period)

        super().__init__(deps, sleep_period=sleep_period)

        self.tx_types = tx_types
        self.only_asset = only_asset

        self.tx_per_batch = int(s_cfg.tx_per_batch)
        self.max_page_deep = int(s_cfg.max_page_deep)
        self.max_age_sec = parse_timespan_to_seconds(s_cfg.max_age)
        self.announce_pending_after_blocks = int(s_cfg.announce_pending_after_blocks)

        self.tx_parser = get_parser_by_network_id(deps.cfg.network_id)
        self.tx_merger = AffiliateTXMerger()

        self.progress_tracker: Optional[tqdm] = None

        self.pending_hash_to_height = {}

        self.deduplicator = TxDeduplicator(deps.db, "scanner:last_seen")

        self.logger.info(f'New TX fetcher is created for {self.tx_types}')

    async def fetch(self):
        await self.deps.db.get_redis()

        txs = await self._fetch_unseen_txs()
        txs = self.merge_related_txs(txs)
        if txs:
            self.logger.info(f'New tx to analyze: {len(txs)}')
        return txs

    async def post_action(self, txs: List[ThorAction]):
        hashes = [self.get_seen_hash(t) for t in txs]
        for h in hashes:
            await self.deduplicator.mark_as_seen(h)

    # -----------------------

    def _update_progress(self, new_txs, total):
        if self.progress_tracker:
            if total and total > 0:
                self.progress_tracker.total = total
            self.progress_tracker.update(new_txs)

    async def _fetch_all_tx_of_type(self,
                                    address=None,
                                    tx_type=None,
                                    max_pages=None,
                                    asset=None,
                                    start_page=0) -> List[ThorAction]:
        page = start_page
        txs = []

        while True:
            q_path = free_url_gen.url_for_tx(
                page * self.tx_per_batch, self.tx_per_batch,
                tx_type=tx_type,
                address=address,
                asset=asset
            )

            if not self.progress_tracker:
                self.logger.info(f"start fetching user's tx: {q_path}")

            j = await self.deps.midgard_connector.request(q_path)
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

    async def fetch_all_tx(self, address=None, liquidity_change_only=False,
                           max_pages=None, start_page=0) -> List[ThorAction]:
        tx_types = free_url_gen.LIQUIDITY_TX_TYPES if liquidity_change_only else [None]

        txs = []
        for tx_type in tx_types:
            this_type_txs = await self._fetch_all_tx_of_type(
                address,
                tx_type=tx_type,
                max_pages=max_pages, start_page=start_page,
                asset=self.only_asset,
            )
            txs.extend(this_type_txs)

        txs.sort(key=lambda tx: tx.height_int)
        self.logger.info(f'User {address = } has {len(txs)} tx ({liquidity_change_only = }).')
        return txs

    def merge_related_txs(self, txs) -> List[ThorAction]:
        txs = self.tx_merger.merge_affiliate_txs(txs)
        return txs

    # -------

    async def fetch_one_batch(self,
                              page=0, txid=None, tx_types=None,
                              asset=None, next_page_token=None) -> Optional[TxParseResult]:
        if next_page_token:
            q_path = free_url_gen.url_for_next_page(next_page_token)
        else:
            q_path = free_url_gen.url_for_tx(page * self.tx_per_batch, self.tx_per_batch, txid=txid, tx_type=tx_types,
                                             asset=asset)

        try:
            j = await self.deps.midgard_connector.request(q_path)
            return self.tx_parser.parse_tx_response(j)
        except (ContentTypeError, AttributeError):
            return None

    async def _fetch_one_batch_tries(self, page, tries) -> Optional[TxParseResult]:
        for _ in range(tries):
            data = await self.fetch_one_batch(page, tx_types=self.tx_types, asset=self.only_asset)
            if data:
                return data
            else:
                self.logger.warning('Retry?')
        self.logger.error('Gave up!')

    @staticmethod
    def _estimate_min_max_height(results, deepest_block_height, top_block_height):
        if results and results.txs:
            deepest_block_height = min(deepest_block_height, min(tx.height_int for tx in results.txs))
            top_block_height = max(top_block_height, max(tx.height_int for tx in results.txs))
        return deepest_block_height, top_block_height

    def _update_pending_txs_here(self, this_batch_pending):
        for tx in this_batch_pending:
            if tx and (tx_hash := tx.tx_hash):
                self.pending_hash_to_height[tx_hash] = tx.height_int

    def _select_old_pending_txs(self, top_block_height, this_batch_pending):
        block_height_threshold = top_block_height - self.announce_pending_after_blocks
        pending_old_txs = [tx for tx in this_batch_pending if tx.height_int < block_height_threshold]
        return pending_old_txs

    def get_pending_hashes_prior_to(self, block_height):
        return [(tx_hash, tx_height)
                for tx_hash, tx_height in self.pending_hash_to_height.items()
                if tx_height < block_height]

    async def try_to_recover_old_txs(self, deepest_block_height):
        try:
            pending_out_of_scope = self.get_pending_hashes_prior_to(deepest_block_height)

            all_txs = []
            for tx_hash, tx_height in pending_out_of_scope:
                self.logger.warning(f'TX {tx_hash} (Blk #{tx_height}) is out of scope. Check it again.')
                tx_results = await self.fetch_one_batch(0, txid=tx_hash)
                if tx_results and (txs := tx_results.txs):
                    self.logger.info(f'Recovered TXs: {txs}')
                    all_txs.extend(txs)

                    if any(t for t in txs if t.is_success):
                        self.logger.info(f'Recovered pending TX {tx_hash} (Blk #{tx_height})')
                        self.pending_hash_to_height.pop(tx_hash)  # remove from pending
            return all_txs
        except Exception as e:
            self.logger.exception(f'Failed to recover old TXs ({e})', stack_info=True)
            return []

    async def _fetch_unseen_txs(self):
        all_txs = []

        deepest_block_height = 1_000_000_000_000_000
        top_block_height = 0

        futures = [
            self._fetch_one_batch_tries(page, tries=self.RETRY_COUNT) for page in range(self.max_page_deep)
        ]

        number_of_pending_txs_this_tick = 0
        cleared_pending_hashes = set()

        # future_tasks = asyncio.as_completed(futures)  # parallel
        # fixme: as we use 9R servers, we have to run sequential fetching in order to avoid 503 errors
        future_tasks = futures  # sequential

        for future in future_tasks:
            # get a batch of TXs
            results = await future

            if results is None:
                self.logger.warning('Got None from Midgard. For now, we just skip it.')
                continue

            # estimate "top_block_height"
            deepest_block_height, top_block_height = self._estimate_min_max_height(
                results, deepest_block_height, top_block_height)

            # filter out old really TXs
            txs = list(self._filter_by_age(results.txs))

            # first, we select only successful TXs
            selected_txs = [tx for tx in txs if tx.is_success]

            # then handle pending TXs
            this_batch_pending = [tx for tx in txs if tx.is_pending]
            self._update_pending_txs_here(this_batch_pending)
            number_of_pending_txs_this_tick += len(this_batch_pending)

            # TXs which are in pending state for quite a long time deserve to be announced with a corresponding mark
            pending_old_txs = self._select_old_pending_txs(top_block_height, this_batch_pending)
            if pending_old_txs:
                # second, we select additionally OLD enough pending TXs
                selected_txs += pending_old_txs

            # filter out TXs from "selected_txs" that have been seen already
            unseen_new_txs = []
            for tx in selected_txs:
                if not await self.deduplicator.have_ever_seen(tx):
                    unseen_new_txs.append(tx)

                    # It was previously pending, but now it's successful
                    if (tx_hash := tx.tx_hash) in self.pending_hash_to_height:
                        del self.pending_hash_to_height[tx_hash]
                        cleared_pending_hashes.add(tx_hash)

            all_txs += unseen_new_txs

        # Take care of pending TXs that were not seen for a long time
        # extra_txs = await self.try_to_recover_old_txs(deepest_block_height)
        # all_txs.extend(extra_txs)

        # Log some stats
        if number_of_pending_txs_this_tick:
            self.logger.info(f'Pending TXs this tick: {number_of_pending_txs_this_tick}.')

        n_accounted_pending = sum(1 for t in all_txs if t.is_pending)
        if n_accounted_pending:
            self.logger.info(f'Pending TXs {n_accounted_pending} are old enough to be counted and announced.')

        if cleared_pending_hashes:
            self.logger.info(f'Pending TXs {cleared_pending_hashes} ({len(cleared_pending_hashes)}) are cleared.')

        return all_txs

    @staticmethod
    def get_seen_hash(tx: ThorAction):
        return tx.tx_hash

    def _filter_by_age(self, txs: List[ThorAction]):
        # do nothing
        if self.max_age_sec == 0:
            return txs

        now = int(now_ts())
        for tx in txs:
            if tx.date_timestamp > now - self.max_age_sec:
                yield tx
