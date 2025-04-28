import json
from typing import Optional

from lib.cooldown import Cooldown
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.runepool import AlertRunePoolAction, AlertPOLState, AlertRunepoolStats, RunepoolState
from notify.dup_stop import TxDeduplicator


class RunePoolTransactionNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        cfg = deps.cfg.runepool.actions
        self.min_usd_amount = cfg.get('min_usd_total', 5000)
        self.cooldown_sec = cfg.as_interval('cooldown', '1h')
        self.cooldown_capacity = cfg.get('cooldown_capacity', 5)
        self.cd = Cooldown(self.deps.db, "RunePoolTxNotification", self.cooldown_sec, self.cooldown_capacity)
        self.deduplicator = TxDeduplicator(deps.db, 'RunePool:announced-hashes')

    async def on_data(self, sender, e: AlertRunePoolAction):
        if e.usd_amount >= self.min_usd_amount:
            if not await self.deduplicator.have_ever_seen_hash(e.tx_hash):
                if await self.cd.can_do():
                    await self.pass_data_to_listeners(e)
                    await self.cd.do()
                    await self.deduplicator.mark_as_seen(e.tx_hash)

    async def reset(self):
        await self.cd.clear()
        await self.deduplicator.clear()


class RunepoolStatsNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        cfg = deps.cfg.runepool.summary

        self.cooldown_sec = cfg.as_interval('cooldown', '1h')
        self.cd = Cooldown(self.deps.db, "RunePoolStatsNotification", self.cooldown_sec)

    DB_KEY_LAST_EVENT = 'runepool:previous_event'

    async def _save_last_event(self, e: RunepoolState):
        if not e:
            self.logger.warning('No event to save')
            return

        data_to_save = e.to_dict()
        data_to_save = json.dumps(data_to_save)
        await self.deps.db.redis.set(self.DB_KEY_LAST_EVENT, data_to_save)

    async def load_last_event(self) -> Optional[RunepoolState]:
        try:
            data = await self.deps.db.redis.get(self.DB_KEY_LAST_EVENT)
            if data:
                data = json.loads(data)
                return RunepoolState.from_json(data)
        except Exception as e:
            self.logger.exception(f'Failed to load last event {e}')

    async def on_data(self, sender, e: AlertPOLState):
        if await self.cd.can_do():
            previous = await self.load_last_event()
            new_event = AlertRunepoolStats(
                e.runepool,
                previous,
                usd_per_rune=self.deps.price_holder.usd_per_rune,
            )
            await self.pass_data_to_listeners(new_event)
            await self._save_last_event(e.runepool)
            await self.cd.do()
