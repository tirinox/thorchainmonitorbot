from services.jobs.scanner.block_loader import BlockResult
from services.lib.db import DB
from services.lib.delegates import INotified, WithDelegates
from services.lib.logs import WithLogger
from services.models.memo import THORMemo, ActionType


class TradeAccEventDecoder(WithLogger, INotified, WithDelegates):
    """
    This class is responsible for decoding deposits and withdrawals from the Trade Accounts.
    """
    def __init__(self, db: DB):
        super().__init__()
        self.redis = db.redis

    async def on_data(self, sender, data: BlockResult):
        transactions = []

        for tx in data.txs:
            if memo := THORMemo.parse_memo(tx.memo):
                if memo.action in (ActionType.TRADE_ACC_WITHDRAW, ActionType.TRADE_ACC_DEPOSIT):
                    transactions.append(tx)

        await self.pass_data_to_listeners(transactions)
