import asyncio

from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.models.bep2 import BEP2CEXFlow, BEP2Transfer
from services.notify.broadcast import Broadcaster


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

    async def _handle_bep2_transfer(self, transfer: BEP2Transfer):
        await self.broadcaster.notify_preconfigured_channels(BaseLocalization.notification_text_bep2_movement, transfer)

    async def _handle_bep2_flow(self, flow: BEP2CEXFlow):
        await self.broadcaster.notify_preconfigured_channels(BaseLocalization.notification_text_cex_flow, flow)

