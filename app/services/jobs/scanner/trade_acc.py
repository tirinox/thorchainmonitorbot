from typing import List

from services.lib.db import DB
from services.lib.delegates import INotified
from services.lib.logs import WithLogger
from services.models.tx import ThorTx


class TradeAccEventDecoder(WithLogger, INotified):
    def __init__(self, db: DB):
        super().__init__()
        self.redis = db.redis

    async def on_data(self, sender, data: List[ThorTx]):
        ...
