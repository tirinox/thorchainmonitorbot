from typing import List

from services.jobs.fetch.base import INotified
from services.lib.date_utils import DAY
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.time_series import TimeSeries
from services.models.tx import ThorTx, ThorTxType


class ILPSummer(INotified):
    MAX_POINTS = 10000

    async def on_data(self, sender, data: List[ThorTx]):
        for tx in data:
            if tx.type == ThorTxType.TYPE_WITHDRAW:
                ilp_rune = tx.meta_withdraw.ilp_rune
                if ilp_rune > 0:
                    await self.time_series.add(ilp_rune=ilp_rune)

        await self.time_series.trim_oldest(self.MAX_POINTS)

    async def ilp_sum(self, period=DAY):
        return await self.time_series.sum(period_sec=period, key='ilp_rune', max_points=self.MAX_POINTS)

    def __init__(self, deps: DepContainer):
        self.logger = class_logger(self)
        self.time_series = TimeSeries('ILP:Paid-On-Withdraw', deps.db)