from typing import Optional

from lib.cooldown import Cooldown
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.trade_acc import AlertTradeAccountAction, AlertTradeAccountStats
from notify.dup_stop import TxDeduplicator


class TradeAccTransactionNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        cfg = deps.cfg.trade_accounts
        self.min_usd_amount = cfg.get('min_usd_total', 5000)
        self.cooldown_sec = cfg.as_interval('cooldown', '1h')
        self.cooldown_capacity = cfg.get('cooldown_capacity', 5)
        self.cd = Cooldown(self.deps.db, "TradeAccTxNotification", self.cooldown_sec, self.cooldown_capacity)
        self.deduplicator = TxDeduplicator(deps.db, 'TradeAcc:announced-hashes')

    async def on_data(self, sender, e: AlertTradeAccountAction):
        if e.usd_amount >= self.min_usd_amount:
            if not await self.deduplicator.have_ever_seen_hash(e.tx_hash):
                if await self.cd.can_do():
                    await self.pass_data_to_listeners(e)
                    await self.cd.do()
                    await self.deduplicator.mark_as_seen(e.tx_hash)

    async def reset(self):
        await self.cd.clear()
        await self.deduplicator.clear()


class TradeAccSummaryNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        cfg = deps.cfg.trade_accounts.summary
        self.cooldown_sec = cfg.as_interval('cooldown', '3d')
        self.cd = Cooldown(self.deps.db, "TradeAccSummaryNotification", self.cooldown_sec)
        self.last_event: Optional[AlertTradeAccountStats] = None

    async def on_data(self, sender, e: AlertTradeAccountStats):
        if not e:
            self.logger.error('Empty event!')

        self.last_event = e
        if await self.cd.can_do():
            await self.pass_data_to_listeners(e)
            await self.cd.do()

    async def reset(self):
        await self.cd.clear()
