from typing import Dict

from aiothornode.types import ThorLastBlock

from services.jobs.fetch.base import INotified
from services.lib.date_utils import DAY
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.time_series import TimeSeries


class BlockHeightNotifier(INotified):
    KEY_SERIES_BLOCK_HEIGHT = 'ThorBlockHeight'

    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)
        self.series = TimeSeries(self.KEY_SERIES_BLOCK_HEIGHT, self.deps.db)
        self.block_height_acc_interval = 60

    async def get_block_time_chart(self, duration_sec=DAY):
        points = await self.series.get_last_values(duration_sec, key='thor_block', with_ts=True)

        if len(points) <= 1:
            return []

        # points: [(ts, block_height)]
        

        # ts_simple_points_to_pandas

        sparse_points = list(TimeSeries.make_sparse_points(points, self.block_height_acc_interval))

        print(f'{sparse_points = }')

        diffs_sparse_points = TimeSeries.adjacent_difference_points(sparse_points)

        return [(t, dh / dt) for t, dt, dh in diffs_sparse_points if dt > 0]

    async def on_data(self, sender, data: Dict[str, ThorLastBlock]):
        thor_block = max(v.thorchain for v in data.values()) if data else 0

        if thor_block > 0:
            await self.series.add(thor_block=thor_block)

        chart = await self.get_block_time_chart()
        print(f'block time chart = {chart}')
