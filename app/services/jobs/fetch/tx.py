from aioredis import Redis

from services.jobs.fetch.base import BaseFetcher
from services.jobs.midgard import get_url_gen_by_network_id, get_parser_by_network_id
from services.lib.datetime import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.models.pool_info import PoolInfo
from services.lib.constants import BUSD_SYMBOL, USDT_SYMBOL, BUSD_TEST_SYMBOL
from services.models.tx import StakeTx
from services.models.pool_stats import StakePoolStats


class TxFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        scfg = deps.cfg.tx.stake_unstake

        sleep_period = parse_timespan_to_seconds(scfg.fetch_period)
        super().__init__(deps, sleep_period=sleep_period)

        self.pool_stat_map = {}
        self.pool_info_map = {}
        self.tx_per_batch = int(scfg.tx_per_batch)
        self.max_page_deep = int(scfg.max_page_deep)
        self.url_gen_midgard = get_url_gen_by_network_id(deps.cfg.network_id)
        self.tx_parser = get_parser_by_network_id(deps.cfg.network_id)

        self.logger.info(f"cfg.tx.stake_unstake: {scfg}")

    async def fetch(self):
        await self.deps.db.get_redis()

        txs = await self._fetch_txs()
        if not txs:
            return []

        await self._load_stats(txs)

        txs = await self._update_pools(txs)
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
        last_seen_hash = await self.get_last_seen_tx_hash()
        for page in range(self.max_page_deep):
            results = await self._fetch_one_batch(self.deps.session, page)
            txs = [tx for tx in results.txs if tx.is_success]
            stop_scan = any(1 for tx in txs if tx.tx_hash == last_seen_hash)
            # fixme: bad algo!
            if stop_scan or not txs:
                self.logger.info(f"no more tx: got {len(all_txs)}")
                break

        new_seen_hash = all_txs[0].tx_hash if all_txs else None
        if new_seen_hash:
            await self.set_last_seen_tx(new_seen_hash)

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
        pool_names.update({
            BUSD_SYMBOL,
            BUSD_TEST_SYMBOL,
            USDT_SYMBOL,
        })  # don't forget BUSD, for total usd volume!
        self.pool_stat_map = {
            pool: (await StakePoolStats.get_from_db(pool, self.deps.db)) for pool in pool_names
        }

    KEY_LAST_SEEN_TX_HASH = 'tx:scanner:last_seen:hash'

    async def get_last_seen_tx_hash(self):
        r: Redis = await self.deps.db.get_redis()
        result = await r.get(self.KEY_LAST_SEEN_TX_HASH)
        return result

    async def set_last_seen_tx(self, hash):
        r: Redis = await self.deps.db.get_redis()
        return await r.set(self.KEY_LAST_SEEN_TX_HASH, hash)

    # 0. PSH = prev seen hash = get()
    # 1. batch = scan a page of TX
    # 2. if PSH in batch: stop scan
    # 3. write the oldest
