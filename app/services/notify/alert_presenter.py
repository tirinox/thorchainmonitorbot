import asyncio

from localization.manager import BaseLocalization
from services.dialog.picture.achievement_picture import AchievementPictureGenerator
from services.dialog.picture.block_height_picture import block_speed_chart
from services.dialog.picture.key_stats_picture import KeyStatsPictureGenerator
from services.dialog.picture.savers_picture import SaversPictureGenerator
from services.jobs.achievement.ach_list import Achievement
from services.lib.constants import THOR_BLOCKS_PER_MINUTE
from services.lib.delegates import INotified
from services.lib.midgard.name_service import NameService
from services.lib.w3.dex_analytics import DexReport
from services.models.flipside import EventKeyStats
from services.models.last_block import EventBlockSpeed, BlockProduceState
from services.models.loans import EventLoanOpen, EventLoanRepayment
from services.models.node_info import NodeSetChanges
from services.models.pol import EventPOL
from services.models.pool_info import PoolChanges
from services.models.events import EventSwapStart
from services.models.savers import EventSaverStats
from services.models.transfer import RuneCEXFlow, RuneTransfer
from services.models.tx import EventLargeTransaction
from services.notify.broadcast import Broadcaster
from services.notify.channel import BoardMessage


class AlertPresenter(INotified):
    def __init__(self, broadcaster: Broadcaster, name_service: NameService):
        self.broadcaster = broadcaster
        self.name_service = name_service

    async def on_data(self, sender, data):
        asyncio.create_task(self._handle_async(data))

    async def _handle_async(self, data):
        if isinstance(data, RuneCEXFlow):
            await self._handle_rune_cex_flow(data)
        elif isinstance(data, RuneTransfer):
            await self._handle_rune_transfer(data)
        elif isinstance(data, EventBlockSpeed):
            await self._handle_block_speed(data)
        elif isinstance(data, EventLargeTransaction):
            await self._handle_large_tx(data)
        elif isinstance(data, DexReport):
            await self._handle_dex_report(data)
        elif isinstance(data, EventSaverStats):
            await self._handle_saver_stats(data)
        elif isinstance(data, PoolChanges):
            await self._handle_pool_churn(data)
        elif isinstance(data, EventPOL):
            await self._handle_pol(data)
        elif isinstance(data, Achievement):
            await self._handle_achievement(data)
        elif isinstance(data, NodeSetChanges):
            await self._handle_node_churn(data)
        elif isinstance(data, EventKeyStats):
            await self._handle_key_stats(data)
        elif isinstance(data, EventSwapStart):
            await self._handle_streaming_swap_start(data)
        elif isinstance(data, (EventLoanOpen, EventLoanRepayment)):
            await self._handle_loans(data)

    # ---- PARTICULARLY ----

    async def _handle_large_tx(self, txs_event: EventLargeTransaction):
        name_map = await self.name_service.safely_load_thornames_from_address_set([
            txs_event.transaction.sender_address
        ])

        await self.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_large_single_tx,
            txs_event.transaction, txs_event.usd_per_rune, txs_event.pool_info, txs_event.cap_info,
            name_map,
            txs_event.mimir,
        )

    async def _handle_rune_transfer(self, transfer: RuneTransfer):
        name_map = await self.name_service.safely_load_thornames_from_address_set([
            transfer.from_addr, transfer.to_addr
        ])

        await self.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_rune_transfer_public,
            transfer, name_map)

    async def _handle_rune_cex_flow(self, flow: RuneCEXFlow):
        await self.broadcaster.notify_preconfigured_channels(BaseLocalization.notification_text_cex_flow, flow)

    @staticmethod
    async def _block_speed_picture_generator(loc: BaseLocalization, points, event):
        chart, chart_name = await block_speed_chart(points, loc,
                                                    normal_bpm=THOR_BLOCKS_PER_MINUTE,
                                                    time_scale_mode='time')

        if event.state in (BlockProduceState.StateStuck, BlockProduceState.Producing):
            caption = loc.notification_text_block_stuck(event)
        else:
            caption = loc.notification_text_block_pace(event)

        return BoardMessage.make_photo(chart, caption=caption, photo_file_name=chart_name)

    async def _handle_block_speed(self, event: EventBlockSpeed):
        await self.broadcaster.notify_preconfigured_channels(self._block_speed_picture_generator, event.points, event)

    async def _handle_dex_report(self, event: DexReport):
        await self.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_dex_report,
            event
        )

    async def _handle_saver_stats(self, event: EventSaverStats):
        async def _gen(loc: BaseLocalization, event):
            pic_gen = SaversPictureGenerator(loc, event)
            pic, pic_name = await pic_gen.get_picture()

            caption = loc.notification_text_saver_stats(event)
            return BoardMessage.make_photo(pic, caption=caption, photo_file_name=pic_name)

        await self.broadcaster.notify_preconfigured_channels(_gen, event)

    async def _handle_pool_churn(self, event: PoolChanges):
        await self.broadcaster.notify_preconfigured_channels(BaseLocalization.notification_text_pool_churn, event)

    async def _handle_achievement(self, event: Achievement):
        async def _gen(loc: BaseLocalization, _a: Achievement):
            pic_gen = AchievementPictureGenerator(loc.ach, _a)
            pic, pic_name = await pic_gen.get_picture()
            caption = loc.ach.notification_achievement_unlocked(event)
            return BoardMessage.make_photo(pic, caption=caption, photo_file_name=pic_name)

        await self.broadcaster.notify_preconfigured_channels(_gen, event)

    async def _handle_pol(self, event: EventPOL):
        # async def _gen(loc: BaseLocalization, _a: EventPOL):
        #     pic_gen = POLPictureGenerator(loc.ach, _a)
        #     pic, pic_name = await pic_gen.get_picture()
        #     caption = loc.ach.notification_pol_stats(event)
        #     return BoardMessage.make_photo(pic, caption=caption, photo_file_name=pic_name)
        # await self.broadcaster.notify_preconfigured_channels(_gen, event)

        # simple text so far
        await self.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_pol_utilization, event
        )

    async def _handle_node_churn(self, event: NodeSetChanges):
        # TEXT
        await self.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_for_node_churn,
            event)

    async def _handle_key_stats(self, event: EventKeyStats):
        # PICTURE
        async def _gen(loc: BaseLocalization, _a: EventKeyStats):
            pic_gen = KeyStatsPictureGenerator(loc, _a)
            pic, pic_name = await pic_gen.get_picture()
            caption = loc.notification_text_key_metrics_caption(event)
            return BoardMessage.make_photo(pic, caption=caption, photo_file_name=pic_name)

        await self.broadcaster.notify_preconfigured_channels(_gen, event)

    async def _handle_streaming_swap_start(self, event: EventSwapStart):
        name_map = await self.name_service.safely_load_thornames_from_address_set([
            event.from_address
        ])

        await self.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_streaming_swap_started,
            event, name_map
        )

    async def _handle_loans(self, data):
        # todo!
        pass
