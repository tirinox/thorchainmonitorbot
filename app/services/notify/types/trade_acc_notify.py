from services.lib.cooldown import Cooldown
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.trade_acc import AlertTradeAccountAction, AlertTradeAccountSummary


class TradeAccTransactionNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        cfg = deps.cfg.trade_accounts
        self.min_usd_amount = cfg.get('min_usd_total', 5000)
        self.cooldown_sec = cfg.as_interval('cooldown', '1h')
        self.cooldown_capacity = cfg.get('cooldown_capacity', 5)
        self.cd = Cooldown(self.deps.db, "TradeAccTxNotification", self.cooldown_sec, self.cooldown_capacity)

    async def on_data(self, sender, e: AlertTradeAccountAction):
        if e.usd_amount >= self.min_usd_amount:
            if await self.cd.can_do():
                await self.pass_data_to_listeners(e)
                await self.cd.do()


class TradeAccSummaryNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        cfg = deps.cfg.trade_accounts.summary
        self.cooldown_sec = cfg.as_interval('cooldown', '1h')
        self.cd = Cooldown(self.deps.db, "TradeAccSummaryNotification", self.cooldown_sec)

    async def on_data(self, sender, e: AlertTradeAccountSummary):
        if await self.cd.can_do():
            await self.pass_data_to_listeners(e)
            await self.cd.do()
