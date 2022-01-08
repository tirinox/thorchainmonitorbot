import logging
import time
from collections import defaultdict
from typing import List, Optional

from aiohttp import ContentTypeError
from aioredis import Redis
from tqdm import tqdm

from services.jobs.fetch.base import BaseFetcher
from services.lib.constants import thor_to_float
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import free_url_gen
from services.models.tx import ThorTx, ThorTxExtended, ThorCoin, ThorMetaSwap, ThorMetaAddLiquidity


class TxFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        s_cfg = deps.cfg.tx
        sleep_period = parse_timespan_to_seconds(s_cfg.fetch_period)
        super().__init__(deps, sleep_period=sleep_period)

        self.tx_per_batch = int(s_cfg.tx_per_batch)
        self.max_page_deep = int(s_cfg.max_page_deep)
        self.max_age_sec = parse_timespan_to_seconds(s_cfg.max_age)

        self.tx_parser = get_parser_by_network_id(deps.cfg.network_id)

        self.progress_tracker: Optional[tqdm] = None

    async def fetch(self):
        await self.deps.db.get_redis()
        txs = await self._fetch_unseen_txs()
        self.logger.info(f'New tx to analyze: {len(txs)}')
        return txs

    async def post_action(self, txs: List[ThorTxExtended]):
        hashes = [t.tx_hash for t in txs]
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
        types = free_url_gen.LIQUIDITY_TX_TYPES_STRING if liquidity_change_only else None
        while True:
            q_path = free_url_gen.url_for_tx(page * self.tx_per_batch, self.tx_per_batch,
                                             types=types,
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
        self.logger.info(f'User {address = } has {len(txs)} tx ({liquidity_change_only = }).')
        return txs

    # -------

    async def _fetch_one_batch(self, page):
        q_path = free_url_gen.url_for_tx(page * self.tx_per_batch, self.tx_per_batch)

        try:
            j = await self.deps.midgard_connector.request_random_midgard(q_path)
            return self.tx_parser.parse_tx_response(j)
        except (ContentTypeError, AttributeError):
            return None

    async def _fetch_unseen_txs(self):
        all_txs = []
        await self.deps.db.get_redis()
        for page in range(self.max_page_deep):
            results = await self._fetch_one_batch(page)

            if results is None:
                continue

            new_txs = results.txs
            new_txs = [tx for tx in new_txs if tx.is_success]  # filter success
            new_txs = list(self._filter_by_age(new_txs))  # filter out old TXs

            # filter out seen TXs
            unseen_new_txs = []
            for tx in new_txs:
                is_seen = await self.is_seen(tx.tx_hash)

                if not is_seen:
                    unseen_new_txs.append(tx)

            if not results.txs:
                self.logger.info(f"no more tx: got {len(all_txs)}")
                break

            all_txs += unseen_new_txs

        all_txs = merge_affiliate_txs(all_txs)

        return all_txs

    def _filter_by_age(self, txs: List[ThorTx]):
        now = int(time.time())
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


logger_aff = logging.getLogger('AffFeeMerger')


def calc_affiliate_fee_from_coins(a: ThorCoin, b: ThorCoin):
    amount_a, amount_b = thor_to_float(a.amount), thor_to_float(b.amount)
    if amount_a == amount_b == 0.0:
        logger_aff.error(f'Both amounts are zero!')
        return 0.0
    return min(amount_a, amount_b) / max(amount_a, amount_b)


def calc_affiliate_fee_percent(tx_a: ThorTx, tx_b: ThorTx):
    in_a, in_b = tx_a.first_input_tx, tx_b.first_input_tx
    if not in_a or not in_b or not in_a.coins or not in_b.coins:
        logger_aff.error(f'Empty input Txs or no coins')
        return 0.0

    coins_a, coins_b = in_a.none_rune_coins, in_b.none_rune_coins
    if coins_a and coins_b:
        coin_a, coin_b = coins_a[0], coins_b[0]
        if coin_a.asset != coin_b.asset:
            logger_aff.error(f'Coin asset mismatch: {coin_a.asset} vs {coin_b.asset}!')
            return 0.0
        return calc_affiliate_fee_from_coins(coin_a, coin_b)

    coin_a, coin_b = in_a.rune_coin, in_b.rune_coin
    return calc_affiliate_fee_from_coins(coin_a, coin_b)


def merge_same_txs(tx1: ThorTx, tx2: ThorTx) -> ThorTx:
    if tx1.type != tx2.type or tx1.pools != tx2.pools:
        logger_aff.warning('Same tx data mismatch, continuing...')
        return tx1

    result_tx, other_tx = tx1, tx2

    try:
        result_tx.affiliate_fee = calc_affiliate_fee_percent(result_tx, other_tx)

        # merge input coins
        for in_i, other_in in enumerate(other_tx.in_tx):
            result_coins = result_tx.in_tx[in_i].coins
            for coin_i, other_coin in enumerate(other_in.coins):
                result_coins[coin_i] = ThorCoin.merge_two(result_coins[coin_i], other_coin)

        # merge meta
        result_tx.meta_swap = ThorMetaSwap.merge_two(result_tx.meta_swap, other_tx.meta_swap)
        result_tx.meta_add = ThorMetaAddLiquidity.merge_two(result_tx.meta_add, other_tx.meta_add)

    except (IndexError, TypeError, ValueError, AssertionError):
        logging.error(f'Cannot merge: {result_tx} and {other_tx}!')

    return result_tx


def merge_affiliate_txs(txs: List[ThorTx]):
    len_before = len(txs)
    same_tx_id_set = defaultdict(list)
    for tx in txs:
        tx.sort_inputs_by_first_asset()
        h = tx.first_input_tx_hash
        if h:
            same_tx_id_set[h].append(tx)

    for h, same_tx_list in same_tx_id_set.items():
        if len(same_tx_list) == 2:
            result_tx = merge_same_txs(*same_tx_list)
            txs = list(filter(lambda a_tx: a_tx.first_input_tx_hash != h, txs))
            txs.append(result_tx)
        elif len(same_tx_list) > 2:
            logger_aff.error(f'> 2 same hash TX ({h})! It is strange! Ignoring them all')
            continue

    txs.sort(key=lambda tx: tx.height_int, reverse=True)

    if len_before > len(txs):
        logger_aff.info(f'Some TXS were merged: {len_before} => {len(txs)}')

    return txs
