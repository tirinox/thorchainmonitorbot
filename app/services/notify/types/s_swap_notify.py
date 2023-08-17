from contextlib import suppress

from aioredis import Redis

from services.jobs.scanner.native_scan import BlockResult
from services.jobs.scanner.swap_start_detector import SwapStartDetector
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger


class StreamingSwapStartTxNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer, prefix='thor'):
        super().__init__()
        self.deps = deps
        self.prefix = prefix
        self.detector = SwapStartDetector(deps)

    KEY_LAST_SEEN_TX_HASH = 'tx:scanner:streaming-swap:seen-start:notify'

    async def has_seen_hash(self, tx_id: str):
        if tx_id:
            r: Redis = self.deps.db.redis
            return await r.sismember(self.KEY_LAST_SEEN_TX_HASH, tx_id)

    async def mark_as_seen(self, tx_id: str):
        if tx_id:
            r: Redis = self.deps.db.redis
            await r.sadd(self.KEY_LAST_SEEN_TX_HASH, tx_id)

    async def on_data(self, sender, data: BlockResult):
        swaps = self.detector.detect_swaps(data)
        for swap_start_ev in swaps:
            if swap_start_ev.is_streaming:
                if not await self.has_seen_hash(tx_id := swap_start_ev.tx_id):
                    await self.pass_data_to_listeners(swap_start_ev)
                    await self.mark_as_seen(tx_id)

    async def clear_seen_cache(self):
        with suppress(Exception):
            r: Redis = self.deps.db.redis
            await r.delete(self.KEY_LAST_SEEN_TX_HASH)
