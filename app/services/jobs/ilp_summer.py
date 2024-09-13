from contextlib import suppress
from typing import List

from services.lib.date_utils import DAY
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.memo import ActionType
from services.models.time_series import TimeSeries
from services.models.tx import ThorTx


class ILPSummer(INotified, WithLogger):
    MAX_POINTS = 10000

    async def on_data(self, sender, data: List[ThorTx]):
        with suppress(Exception):  # This must not break the rest of the pipeline! So ignore everything bad
            for tx in data:
                if tx.is_of_type(ActionType.WITHDRAW):
                    ilp_rune = tx.meta_withdraw.ilp_rune
                    if ilp_rune > 0:
                        await self.time_series.add(ilp_rune=ilp_rune)

            # await self.time_series.trim_oldest(self.MAX_POINTS)

    async def ilp_sum(self, period=DAY):
        return await self.time_series.sum(period_sec=period, key='ilp_rune', max_points=self.MAX_POINTS)

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.time_series = TimeSeries('ILP:Paid-On-Withdraw', deps.db, self.MAX_POINTS)
