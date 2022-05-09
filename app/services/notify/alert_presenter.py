import asyncio

from localization import BaseLocalization
from services.dialog.picture.block_height_picture import block_speed_chart
from services.jobs.fetch.base import INotified
from services.lib.constants import THOR_BLOCKS_PER_MINUTE
from services.models.bep2 import BEP2CEXFlow, BEP2Transfer
from services.models.last_block import EventBlockSpeed, BlockProduceState
from services.notify.broadcast import Broadcaster
from services.notify.channel import BoardMessage


class AlertPresenter(INotified):
    def __init__(self, broadcaster: Broadcaster):
        self.broadcaster = broadcaster

    async def on_data(self, sender, data):
        asyncio.create_task(self._handle_async(data))

    async def _handle_async(self, data):
        if isinstance(data, BEP2CEXFlow):
            await self._handle_bep2_flow(data)
        elif isinstance(data, BEP2Transfer):
            await self._handle_bep2_transfer(data)
        elif isinstance(data, EventBlockSpeed):
            await self._handle_block_speed(data)

    # ---- PARTICULARLY ----

    async def _handle_bep2_transfer(self, transfer: BEP2Transfer):
        await self.broadcaster.notify_preconfigured_channels(BaseLocalization.notification_text_bep2_movement, transfer)

    async def _handle_bep2_flow(self, flow: BEP2CEXFlow):
        await self.broadcaster.notify_preconfigured_channels(BaseLocalization.notification_text_cex_flow, flow)

    async def _handle_block_speed(self, event: EventBlockSpeed):
        async def gen_fun(loc: BaseLocalization, points):
            chart = await block_speed_chart(points, loc, normal_bpm=THOR_BLOCKS_PER_MINUTE, time_scale_mode='time')
            if event.state in (BlockProduceState.StateStuck, BlockProduceState.Producing):
                caption = loc.notification_text_block_stuck(event)
            else:
                caption = loc.notification_text_block_pace(event)

            return BoardMessage.make_photo(chart, caption=caption)

        await self.broadcaster.notify_preconfigured_channels(gen_fun, event.points)
