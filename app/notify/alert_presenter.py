import asyncio
from typing import Union

from api.midgard.name_service import NameService, NameMap
from api.w3.dex_analytics import DexReport
from comm.localization.manager import BaseLocalization
from comm.picture.achievement_picture import build_achievement_picture_generator
from comm.picture.block_height_picture import block_speed_chart
from comm.picture.burn_picture import rune_burn_graph
from comm.picture.key_stats_picture import KeyStatsPictureGenerator
from comm.picture.nodes_pictures import NodePictureGenerator
from comm.picture.pools_picture import PoolPictureGenerator
from comm.picture.price_picture import price_graph_from_db
from comm.picture.queue_picture import queue_graph
from comm.picture.savers_picture import SaversPictureGenerator
from comm.picture.supply_picture import SupplyPictureGenerator
from jobs.achievement.ach_list import Achievement
from jobs.fetch.chain_id import AlertChainIdChange
from lib.constants import THOR_BLOCKS_PER_MINUTE
from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.draw_utils import img_to_bio
from lib.html_renderer import InfographicRendererRPC
from lib.logs import WithLogger
from lib.utils import namedtuple_to_dict
from models.cap_info import AlertLiquidityCap
from models.circ_supply import EventRuneBurn
from models.key_stats_model import AlertKeyStats
from models.last_block import EventBlockSpeed, BlockProduceState
from models.loans import AlertLoanOpen, AlertLoanRepayment, AlertLendingStats, AlertLendingOpenUpdate
from models.mimir import AlertMimirChange, AlertMimirVoting
from models.node_info import AlertNodeChurn
from models.pool_info import PoolChanges, PoolMapPair
from models.price import AlertPrice, RuneMarketInfo, AlertPriceDiverge
from models.queue import AlertQueue
from models.runepool import AlertPOLState, AlertRunepoolStats
from models.runepool import AlertRunePoolAction
from models.s_swap import AlertSwapStart
from models.savers import AlertSaverStats
from models.trade_acc import AlertTradeAccountAction, AlertTradeAccountStats
from models.transfer import RuneCEXFlow, RuneTransfer
from models.tx import EventLargeTransaction
from models.version import AlertVersionUpgradeProgress, AlertVersionChanged
from notify.broadcast import Broadcaster
from notify.channel import BoardMessage, MessageType
from notify.public.chain_notify import AlertChainHalt


class AlertPresenter(INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.broadcaster: Broadcaster = deps.broadcaster
        self.name_service: NameService = deps.name_service
        self.renderer = InfographicRendererRPC(deps)
        self.use_renderer = deps.cfg.get_pure('user_html_renderer', False)

    async def on_data(self, sender, data):
        # noinspection PyAsyncCall
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
        elif isinstance(data, AlertSaverStats):
            await self._handle_saver_stats(data)
        elif isinstance(data, PoolChanges):
            await self._handle_pool_churn(data)
        elif isinstance(data, AlertPOLState):
            await self._handle_pol(data)
        elif isinstance(data, Achievement):
            await self._handle_achievement(data)
        elif isinstance(data, AlertNodeChurn):
            await self._handle_node_churn(data)
        elif isinstance(data, AlertKeyStats):
            await self._handle_key_stats(data)
        elif isinstance(data, AlertSwapStart):
            await self._handle_streaming_swap_start(data)
        elif isinstance(data, (AlertLoanOpen, AlertLoanRepayment)):
            await self._handle_loans(data)
        elif isinstance(data, AlertLendingOpenUpdate):
            await self._handle_lending_caps(data)
        elif isinstance(data, AlertPrice):
            await self._handle_price(data)
        elif isinstance(data, AlertMimirChange):
            await self._handle_mimir(data)
        elif isinstance(data, AlertChainHalt):
            await self._handle_chain_halt(data)
        elif isinstance(data, AlertLendingStats):
            await self._handle_lending_stats(data)
        elif isinstance(data, PoolMapPair):
            await self._handle_best_pools(data)
        elif isinstance(data, AlertTradeAccountAction):
            await self._handle_trace_account_move(data)
        elif isinstance(data, AlertTradeAccountStats):
            await self._handle_trace_account_summary(data)
        elif isinstance(data, AlertRunePoolAction):
            await self._handle_runepool_action(data)
        elif isinstance(data, AlertRunepoolStats):
            await self._handle_runepool_stats(data)
        elif isinstance(data, AlertChainIdChange):
            await self._handle_chain_id(data)
        elif isinstance(data, RuneMarketInfo):
            await self._handle_supply(data)
        elif isinstance(data, AlertVersionChanged):
            await self._handle_version_changed(data)
        elif isinstance(data, AlertVersionUpgradeProgress):
            await self._handle_version_upgrade_progress(data)
        elif isinstance(data, AlertMimirVoting):
            await self._handle_mimir_voting(data)
        elif isinstance(data, AlertQueue):
            await self._handle_queue(data)
        elif isinstance(data, AlertLiquidityCap):
            await self._handle_liquidity_cap(data)
        elif isinstance(data, EventRuneBurn):
            await self._handle_rune_burn(data)

    async def load_names(self, addresses) -> NameMap:
        if isinstance(addresses, str):
            addresses = (addresses,)

        return await self.name_service.safely_load_thornames_from_address_set(addresses)

    # ---- PARTICULARLY ----

    async def _handle_large_tx(self, tx_event: EventLargeTransaction):
        name_map = await self.load_names(tx_event.transaction.all_addresses)

        await self.broadcaster.broadcast_to_all(
            BaseLocalization.notification_text_large_single_tx,
            tx_event, name_map
        )

    async def _handle_rune_transfer(self, transfer: RuneTransfer):
        name_map = await self.load_names([
            transfer.from_addr, transfer.to_addr
        ])

        await self.broadcaster.broadcast_to_all(
            BaseLocalization.notification_text_rune_transfer_public,
            transfer, name_map)

    async def _handle_rune_cex_flow(self, flow: RuneCEXFlow):
        await self.broadcaster.broadcast_to_all(BaseLocalization.notification_text_cex_flow, flow)

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
        await self.broadcaster.broadcast_to_all(self._block_speed_picture_generator, event.points, event)

    async def _handle_dex_report(self, event: DexReport):
        await self.broadcaster.broadcast_to_all(
            BaseLocalization.notification_text_dex_report,
            event
        )

    async def _handle_saver_stats(self, event: AlertSaverStats):
        async def _gen(loc: BaseLocalization, event):
            pic_gen = SaversPictureGenerator(loc, event)
            pic, pic_name = await pic_gen.get_picture()

            caption = loc.notification_text_saver_stats(event)
            return BoardMessage.make_photo(pic, caption=caption, photo_file_name=pic_name)

        await self.broadcaster.broadcast_to_all(_gen, event)

    async def _handle_pool_churn(self, event: PoolChanges):
        await self.broadcaster.broadcast_to_all(BaseLocalization.notification_text_pool_churn, event)

    async def _handle_achievement(self, event: Achievement):
        async def _gen(loc: BaseLocalization, _a: Achievement):
            pic_gen = build_achievement_picture_generator(_a, loc.ach)
            pic, pic_name = await pic_gen.get_picture()
            caption = loc.ach.notification_achievement_unlocked(event)
            return BoardMessage.make_photo(pic, caption=caption, photo_file_name=pic_name)

        await self.broadcaster.broadcast_to_all(_gen, event)

    async def _handle_pol(self, event: AlertPOLState):
        # async def _gen(loc: BaseLocalization, _a: EventPOL):
        #     pic_gen = POLPictureGenerator(loc.ach, _a)
        #     pic, pic_name = await pic_gen.get_picture()
        #     caption = loc.ach.notification_pol_stats(event)
        #     return BoardMessage.make_photo(pic, caption=caption, photo_file_name=pic_name)
        # await self.broadcaster.notify_preconfigured_channels(_gen, event)

        # simple text so far
        await self.broadcaster.broadcast_to_all(
            BaseLocalization.notification_text_pol_stats, event
        )

    async def _handle_node_churn(self, event: AlertNodeChurn):
        if event.finished:
            await self.broadcaster.broadcast_to_all(
                BaseLocalization.notification_text_node_churn_finish,
                event.changes)

            if event.with_picture:
                async def _gen(loc: BaseLocalization):
                    gen = NodePictureGenerator(event.network_info, event.bond_chart, loc)
                    pic = await gen.generate()
                    bio_graph = img_to_bio(pic, gen.proper_name())
                    caption = loc.PIC_NODE_DIVERSITY_BY_PROVIDER_CAPTION
                    return BoardMessage.make_photo(bio_graph, caption)

                await self.broadcaster.broadcast_to_all(_gen)

        else:
            # started
            await self.broadcaster.broadcast_to_all(
                BaseLocalization.notification_churn_started,
                event.changes
            )

    async def _handle_key_stats(self, event: AlertKeyStats):
        # PICTURE
        async def _gen(loc: BaseLocalization, _a: AlertKeyStats):
            pic_gen = KeyStatsPictureGenerator(loc, _a)
            pic, pic_name = await pic_gen.get_picture()
            caption = loc.notification_text_key_metrics_caption(event)
            return BoardMessage.make_photo(pic, caption=caption, photo_file_name=pic_name)

        await self.broadcaster.broadcast_to_all(_gen, event)

    async def _handle_streaming_swap_start(self, event: AlertSwapStart):
        name_map = await self.load_names(event.from_address)

        await self.broadcaster.broadcast_to_all(
            BaseLocalization.notification_text_streaming_swap_started,
            event, name_map
        )

    async def _handle_loans(self, event: Union[AlertLoanOpen, AlertLoanRepayment]):
        name_map = await self.load_names(event.loan.owner)

        if isinstance(event, AlertLoanOpen):
            method = BaseLocalization.notification_text_loan_open
        else:
            method = BaseLocalization.notification_text_loan_repayment

        await self.broadcaster.broadcast_to_all(
            method,
            event, name_map
        )

    async def _handle_price(self, event: AlertPrice):
        async def price_graph_gen(loc: BaseLocalization):
            # todo: fix self.deps reference
            graph, graph_name = await price_graph_from_db(self.deps, loc, event.price_graph_period)
            caption = loc.notification_text_price_update(event)
            return BoardMessage.make_photo(graph, caption=caption, photo_file_name=graph_name)

        if event.is_ath and event.ath_sticker:
            await self.broadcaster.broadcast_to_all(BoardMessage(event.ath_sticker, MessageType.STICKER))

        await self.broadcaster.broadcast_to_all(price_graph_gen)

    async def _handle_chain_halt(self, event: AlertChainHalt):
        await self.broadcaster.broadcast_to_all(
            BaseLocalization.notification_text_trading_halted_multi,
            event.changed_chains
        )

    async def _handle_mimir(self, data: AlertMimirChange):
        await self.deps.broadcaster.broadcast_to_all(
            BaseLocalization.notification_text_mimir_changed,
            data.changes,
            data.holder,
        )

    async def _handle_lending_stats(self, data: AlertLendingStats):
        await self.deps.broadcaster.broadcast_to_all(
            BaseLocalization.notification_lending_stats,
            data,
        )

    async def _handle_lending_caps(self, data: AlertLendingOpenUpdate):
        await self.deps.broadcaster.broadcast_to_all(
            BaseLocalization.notification_lending_open_back_up,
            data,
        )

    async def _handle_best_pools(self, data: PoolMapPair):
        async def generate_pool_picture(loc: BaseLocalization, event: PoolMapPair):
            pic_gen = PoolPictureGenerator(loc, event)
            pic, pic_name = await pic_gen.get_picture()
            caption = loc.notification_text_best_pools(event, 5)
            return BoardMessage.make_photo(pic, caption=caption, photo_file_name=pic_name)

        await self.deps.broadcaster.broadcast_to_all(generate_pool_picture, data)

    async def _handle_trace_account_move(self, data: AlertTradeAccountAction):
        name_map = await self.load_names([data.actor, data.destination_address])
        await self.deps.broadcaster.broadcast_to_all(
            BaseLocalization.notification_text_trade_account_move,
            data,
            name_map
        )

    async def _handle_trace_account_summary(self, data: AlertTradeAccountStats):
        await self.deps.broadcaster.broadcast_to_all(
            BaseLocalization.notification_text_trade_account_summary,
            data,
        )

    async def _handle_runepool_action(self, data: AlertRunePoolAction):
        name_map = await self.load_names([data.actor, data.destination_address])
        await self.deps.broadcaster.broadcast_to_all(
            BaseLocalization.notification_runepool_action,
            data,
            name_map
        )

    async def _handle_runepool_stats(self, data: AlertRunepoolStats):
        await self.deps.broadcaster.broadcast_to_all(BaseLocalization.notification_runepool_stats, data)

    async def _handle_chain_id(self, data: AlertChainIdChange):
        await self.deps.broadcaster.broadcast_to_all(BaseLocalization.notification_text_chain_id_changed, data)

    async def _handle_supply(self, market_info: RuneMarketInfo):
        async def supply_pic_gen(loc: BaseLocalization):
            gen = SupplyPictureGenerator(loc, market_info.supply_info, self.deps.net_stats)
            pic, pic_name = await gen.get_picture()
            return BoardMessage.make_photo(pic, loc.SUPPLY_PIC_CAPTION, pic_name)

        await self.deps.broadcaster.broadcast_to_all(BaseLocalization.text_metrics_supply,
                                                     market_info)
        await self.deps.broadcaster.broadcast_to_all(supply_pic_gen)

    async def _handle_version_upgrade_progress(self, data: AlertVersionUpgradeProgress):
        await self.deps.broadcaster.broadcast_to_all(
            BaseLocalization.notification_text_version_changed_progress,
            data
        )

    async def _handle_version_changed(self, data: AlertVersionChanged):
        await self.deps.broadcaster.broadcast_to_all(BaseLocalization.notification_text_version_changed, data)

    async def _handle_mimir_voting(self, e: AlertMimirVoting):
        await self.deps.broadcaster.broadcast_to_all(BaseLocalization.notification_text_mimir_voting_progress, e)

    async def _handle_queue(self, e: AlertQueue):
        photo_name = ''
        if e.with_picture:
            photo, photo_name = await queue_graph(self.deps, self.deps.loc_man.default)
        else:
            photo = None

        async def message_gen(loc: BaseLocalization):
            text = loc.notification_text_queue_update(e.item_type, e.is_free, e.value)
            if photo is not None:
                return BoardMessage.make_photo(photo, text, photo_name)
            else:
                return text

        await self.deps.broadcaster.broadcast_to_all(message_gen)

    async def _handle_liquidity_cap(self, data: AlertLiquidityCap):
        f = BaseLocalization.notification_text_cap_full if data.is_full \
            else BaseLocalization.notification_text_cap_opened_up
        await self.deps.broadcaster.broadcast_to_all(f, data.cap)

    async def _handle_price_divergence(self, data: AlertPriceDiverge):
        await self.deps.broadcaster.broadcast_to_all(BaseLocalization.notification_text_price_divergence, data)

    async def _handle_rune_burn(self, data: EventRuneBurn):
        async def message_gen(loc: BaseLocalization):
            text = loc.notification_rune_burn(data)

            if self.use_renderer:
                # todo: share EventRuneBurn between the components, use Pydantic
                photo = await self.renderer.render('rune_burn_and_income.jinja2', namedtuple_to_dict(data))
            else:
                # old style
                photo, photo_name = await rune_burn_graph(data.points, loc, days=data.tally_days)

            if photo is not None:
                return BoardMessage.make_photo(photo, text, 'rune_burnt.png')
            else:
                return text

        await self.deps.broadcaster.broadcast_to_all(message_gen)
