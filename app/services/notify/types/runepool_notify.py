from services.lib.cooldown import Cooldown
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.runepool import AlertRunePoolAction
from services.notify.dup_stop import TxDeduplicator


class RunePoolTransactionNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        cfg = deps.cfg.runepool
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
