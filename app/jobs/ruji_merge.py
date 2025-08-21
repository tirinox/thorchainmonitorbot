import json
from datetime import datetime, timedelta
from typing import Optional

from api.aionode.types import thor_to_float
from jobs.fetch.ruji_merge import RujiMergeStatsFetcher
from jobs.scanner.block_result import BlockResult
from jobs.scanner.tx import NativeThorTx
from jobs.scanner.wasm_execute import CosmwasmExecuteDecoder
from lib.cache import async_cache_ignore_arguments
from lib.delegates import WithDelegates, INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.ruji import EventRujiMerge, MergeSystem


class RujiMergeTracker(WithDelegates, INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.decoder = CosmwasmExecuteDecoder(MergeSystem.RUJI_MERGE_CONTRACTS)
        self.stats_fetcher = RujiMergeStatsFetcher(deps)

    async def on_data(self, sender, block: BlockResult):
        events = await self.get_events_from_block(block)
        for ev in events:
            await self._store_event(ev)
            await self.pass_data_to_listeners(ev)

    @async_cache_ignore_arguments(ttl=120)
    async def get_merge_system(self):
        return await self.stats_fetcher.fetch()

    DB_PREFIX = "Rujira:Merge:Tracker"

    def key(self, now: float):
        dt = datetime.fromtimestamp(now)
        return f'{self.DB_PREFIX}:{dt.strftime("%Y-%m-%d")}'

    def keys_for_days(self, now: float, days_back: int):
        dt = datetime.fromtimestamp(now)
        return [
            self.key((dt - timedelta(days=d)).timestamp()) for d in range(days_back, -1, -1)
        ]

    async def clear(self):
        r = await self.deps.db.get_redis()
        async for key in r.scan_iter(match=f"{self.DB_PREFIX}:*"):
            await r.delete(key)

    def tx_to_merge_event(self, tx: NativeThorTx, system: MergeSystem) -> Optional[EventRujiMerge]:
        funds = tx.first_message.contract_funds
        if len(funds) != 1:
            self.logger.error(f"Merge Tx {tx.tx_hash} has {len(funds)} funds, expected 1!")
            return None

        asset = funds[0]["denom"].upper()
        amount = thor_to_float(funds[0]["amount"])

        contract = system.find_contract_by_denom(asset)
        if not contract:
            self.logger.error(f"Merge Tx {tx.tx_hash} has unknown asset {asset}")
            return None

        merge_event = tx.find_events_by_type("wasm-rujira-merge/deposit")
        if not merge_event:
            self.logger.error(f"Merge Tx {tx.tx_hash} has no merge event")
            return None

        shares = thor_to_float(merge_event[0].get("shares"))

        volume_usd = amount * contract.price_usd
        rate = shares / amount
        decay_factor = float(contract.config.calculate_decay(amount, shares))

        return EventRujiMerge(
            tx_id=tx.tx_hash,
            height=tx.height,
            from_address=tx.first_signer_address,
            from_address_name="",
            volume_usd=volume_usd,
            amount=amount,
            asset=asset,
            rate=rate,
            decay_factor=round(decay_factor, 5),
            timestamp=tx.timestamp,
        )

    async def get_events_from_block(self, block: BlockResult):
        txs = list(self.decoder.decode(block))
        system = await self.get_merge_system()
        if not system:
            self.logger.error("Failed to fetch merge system data")
            return []

        return [self.tx_to_merge_event(tx, system) for tx in txs if tx.is_success]

    async def _store_event(self, ev: EventRujiMerge):
        await self.deps.db.redis.hset(self.key(ev.timestamp), ev.tx_id, json.dumps(ev.to_dict()))

    async def get_all_events_from_db(self, now: float, days_back: int = 0):
        r = await self.deps.db.get_redis()
        keys = self.keys_for_days(now, days_back)
        results = []
        for key in keys:
            data = await r.hgetall(key)
            results.extend(EventRujiMerge.from_dict(json.loads(v)) for k, v in data.items())
        return results

    async def get_top_events_from_db(self, now: float, days_back: int, limit=10):
        events = await self.get_all_events_from_db(now, days_back)
        events.sort(key=lambda x: x.volume_usd, reverse=True)
        return events[:limit]
