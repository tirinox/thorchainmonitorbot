from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import *
from aiogram.utils.helper import HelperMode

from comm.localization.manager import BaseLocalization
from jobs.fetch.fair_price import RuneMarketInfoFetcher
from jobs.fetch.node_info import NodeInfoFetcher
from lib.constants import THOR_BLOCKS_PER_MINUTE
from lib.date_utils import DAY, HOUR, parse_timespan_to_seconds, now_ts
from lib.draw_utils import img_to_bio
from lib.texts import kbd
from models.net_stats import AlertNetworkStats
from models.node_info import NodeInfo
from models.price import AlertPrice
from notify.public.best_pool_notify import BestPoolsNotifier
from notify.public.block_notify import BlockHeightNotifier
from notify.public.burn_notify import BurnNotifier
from notify.public.cap_notify import LiquidityCapNotifier
from notify.public.node_churn_notify import NodeChurnNotifier
from notify.public.price_notify import PriceNotifier
from notify.public.stats_notify import NetworkStatsNotifier
from notify.public.transfer_notify import RuneMoveNotifier
from .base import BaseDialog, message_handler
from comm.picture.block_height_picture import block_speed_chart
from comm.picture.key_stats_picture import KeyStatsPictureGenerator
from comm.picture.nodes_pictures import NodePictureGenerator
from comm.picture.pools_picture import PoolPictureGenerator
from comm.picture.price_picture import price_graph_from_db
from comm.picture.queue_picture import queue_graph
from comm.picture.savers_picture import SaversPictureGenerator
from comm.picture.supply_picture import SupplyPictureGenerator
from ..picture.burn_picture import rune_burn_graph


class MetricsStates(StatesGroup):
    mode = HelperMode.snake_case

    SECTION_FINANCE = State()
    SECTION_NET_OP = State()

    MAIN_METRICS_MENU = State()

    GENERIC_DURATION = State()


class MetricsDialog(BaseDialog):
    # ----------- HANDLERS ------------

    @message_handler(state=MetricsStates.MAIN_METRICS_MENU)
    async def handle_main_state(self, message: Message):
        if message.text == self.loc.BUTTON_BACK:
            await self.go_back(message)
            return
        elif message.text == self.loc.BUTTON_METR_S_NET_OP:
            await self.on_menu_net_op(message)
        elif message.text == self.loc.BUTTON_METR_S_FINANCIAL:
            await self.on_menu_financial(message)
        else:
            await self.show_main_menu(message)

    async def show_main_menu(self, message: Message):
        await MetricsStates.MAIN_METRICS_MENU.set()
        reply_markup = kbd([
            [self.loc.BUTTON_METR_S_FINANCIAL, self.loc.BUTTON_METR_S_NET_OP],
            [self.loc.BUTTON_BACK],
        ])
        await message.answer(self.loc.TEXT_METRICS_INTRO,
                             reply_markup=reply_markup,
                             disable_notification=True)

    async def show_menu_financial(self, message: Message):
        await MetricsStates.SECTION_FINANCE.set()
        reply_markup = kbd([
            [self.loc.BUTTON_METR_PRICE, self.loc.BUTTON_METR_POL, self.loc.BUTTON_METR_STATS],
            [self.loc.BUTTON_METR_SAVERS, self.loc.BUTTON_METR_TOP_POOLS, self.loc.BUTTON_METR_CEX_FLOW],
            [self.loc.BUTTON_METR_SUPPLY, self.loc.BUTTON_METR_DEX_STATS, self.loc.BUTTON_BACK],
        ])
        await message.answer(self.loc.TEXT_METRICS_INTRO,
                             reply_markup=reply_markup,
                             disable_notification=True)

    async def show_menu_net_op(self, message: Message):
        await MetricsStates.SECTION_NET_OP.set()
        reply_markup = kbd([
            [self.loc.BUTTON_METR_NODES, self.loc.BUTTON_METR_VOTING, self.loc.BUTTON_METR_MIMIR],
            [self.loc.BUTTON_METR_BLOCK_TIME, self.loc.BUTTON_METR_QUEUE, self.loc.BUTTON_METR_CHAINS],
            [self.loc.BUTTON_BACK],
        ])
        await message.answer(self.loc.TEXT_METRICS_INTRO,
                             reply_markup=reply_markup,
                             disable_notification=True)

    @message_handler(state=MetricsStates.SECTION_FINANCE)
    async def on_menu_financial(self, message: Message):
        back_state = 'financial'
        if message.text == self.loc.BUTTON_BACK:
            await self.show_main_menu(message)
            return
        elif message.text == self.loc.BUTTON_METR_PRICE:
            await self.ask_generic_duration(message, 'price', back_state)
            return
        elif message.text == self.loc.BUTTON_METR_POL:
            await self.show_pol(message)
        elif message.text == self.loc.BUTTON_METR_STATS:
            await self.show_last_stats(message)
        elif message.text == self.loc.BUTTON_METR_SAVERS:
            await self.show_savers(message)
        elif message.text == self.loc.BUTTON_METR_TOP_POOLS:
            await self.show_top_pools(message)
        elif message.text == self.loc.BUTTON_METR_CEX_FLOW:
            await self.ask_generic_duration(message, 'cex_flow', back_state)
            return
        elif message.text == self.loc.BUTTON_METR_SUPPLY:
            await self.show_rune_supply(message)
        elif message.text == self.loc.BUTTON_METR_DEX_STATS:
            await self.ask_generic_duration(message, 'dex_aggr', back_state)
            return
        await self.show_menu_financial(message)

    @message_handler(state=MetricsStates.SECTION_NET_OP)
    async def on_menu_net_op(self, message: Message):
        back_state = 'net_op'
        if message.text == self.loc.BUTTON_BACK:
            await self.show_main_menu(message)
            return
        elif message.text == self.loc.BUTTON_METR_QUEUE:
            await self.ask_generic_duration(message, 'queue', back_state)
            return
        elif message.text == self.loc.BUTTON_METR_NODES:
            await self.show_node_list(message)
        elif message.text == self.loc.BUTTON_METR_CHAINS:
            await self.show_chain_info(message)
        elif message.text == self.loc.BUTTON_METR_MIMIR:
            await self.show_mimir_info(message)
        elif message.text == self.loc.BUTTON_METR_VOTING:
            await self.show_voting_info(message)
        elif message.text == self.loc.BUTTON_METR_BLOCK_TIME:
            await self.ask_generic_duration(message, 'block_time', back_state)
            return
        await self.show_menu_net_op(message)

    async def show_cap(self, message: Message):
        info = await LiquidityCapNotifier.get_last_cap_from_db(self.deps.db)
        await message.answer(self.loc.cap_message(info),
                             disable_web_page_preview=True,
                             disable_notification=True)

    async def show_savers(self, message: Message):
        await self.start_typing(message)

        event = await self.deps.saver_stats_fetcher.get_savers_event_cached()

        if not event or not event.current_stats or not event.current_stats.vaults:
            await message.answer(self.loc.TEXT_SAVERS_NO_DATA,
                                 disable_notification=True)
            return

        pic_gen = SaversPictureGenerator(self.loc, event)
        pic, name = await pic_gen.get_picture()

        await message.answer_photo(img_to_bio(pic, name),
                                   caption=self.loc.notification_text_saver_stats(event),
                                   disable_notification=True)

    async def show_last_stats(self, message: Message):
        await self.start_typing(message)

        nsn = NetworkStatsNotifier(self.deps)
        old_info = await nsn.get_previous_stats()
        new_info = self.deps.net_stats

        loc: BaseLocalization = self.loc
        if not new_info.is_ok:
            await message.answer(f"{loc.ERROR} {loc.NOT_READY}", disable_notification=True)
            return

        await message.answer(
            loc.notification_text_network_summary(
                AlertNetworkStats(
                    old_info, new_info,
                    self.deps.node_holder.nodes
                ),
            ),
            disable_web_page_preview=True,
            disable_notification=True
        )

    async def show_node_list(self, message: Message):
        await self.start_typing(message)

        node_fetcher = NodeInfoFetcher(self.deps)
        result_network_info = await node_fetcher.get_node_list_and_geo_info()  # todo: switch to NodeChurnDetector (DB)
        node_list = result_network_info.node_info_list

        active_node_messages = self.loc.node_list_text(node_list, NodeInfo.ACTIVE)
        standby_node_messages = self.loc.node_list_text(node_list, NodeInfo.STANDBY)
        other_node_messages = self.loc.node_list_text(node_list, 'others')

        for message_text in (active_node_messages + standby_node_messages + other_node_messages):
            if message_text:
                await message.answer(message_text, disable_web_page_preview=True, disable_notification=True)

        # generate a beautiful masterpiece :)
        chart_pts = await NodeChurnNotifier(self.deps).load_last_statistics(NodePictureGenerator.CHART_PERIOD)
        gen = NodePictureGenerator(result_network_info, chart_pts, self.loc)
        pic = await gen.generate()

        await message.answer_photo(img_to_bio(pic, gen.proper_name()), disable_notification=True)

    async def show_queue(self, message, period):
        await self.start_typing(message)

        queue_info = self.deps.queue_holder
        plot, plot_name = await queue_graph(self.deps, self.loc, duration=period)
        if plot is not None:
            plot_bio = img_to_bio(plot, plot_name)
            await message.answer_photo(plot_bio, caption=self.loc.queue_message(queue_info), disable_notification=True)
        else:
            await message.answer(self.loc.queue_message(queue_info), disable_notification=True)

    async def show_price(self, message, period):
        await self.start_typing(message)

        market_info = await self.deps.rune_market_fetcher.fetch()

        if not market_info:
            await message.answer(self.loc.TEXT_PRICE_NO_DATA, disable_notification=True)
            return

        pn = PriceNotifier(self.deps)
        price_1h, price_24h, price_7d = await pn.historical_get_triplet()
        market_info.pool_rune_price = self.deps.price_holder.usd_per_rune
        btc_price = self.deps.price_holder.btc_per_rune

        price_text = self.loc.notification_text_price_update(AlertPrice(
            price_1h, price_24h, price_7d,
            market_info=market_info,
            last_ath=None, is_ath=False,
            btc_pool_rune_price=btc_price,
            halted_chains=self.deps.halted_chains
        ))

        graph, graph_name = await price_graph_from_db(self.deps, self.loc, period=period)
        await message.answer_photo(img_to_bio(graph, graph_name),
                                   disable_notification=True)
        await message.answer(price_text,
                             disable_web_page_preview=True,
                             disable_notification=True)

    async def show_chain_info(self, message: Message):
        await self.start_typing(message)

        text = self.loc.text_chain_info(list(self.deps.chain_info.values()))
        await message.answer(text,
                             disable_web_page_preview=True,
                             disable_notification=True)

    async def show_mimir_info(self, message: Message):
        await self.start_typing(message)

        texts = self.loc.text_mimir_info(self.deps.mimir_const_holder)
        for text in texts:
            await message.answer(text,
                                 disable_web_page_preview=True,
                                 disable_notification=True)

    async def show_voting_info(self, message: Message):
        await self.start_typing(message)

        texts = self.loc.text_node_mimir_voting(self.deps.mimir_const_holder)
        for text in texts:
            await message.answer(text,
                                 disable_web_page_preview=True,
                                 disable_notification=True)

    async def show_block_time(self, message: Message, period=2 * DAY):
        await self.start_typing(message)

        block_notifier: BlockHeightNotifier = self.deps.block_notifier
        points = await block_notifier.get_block_time_chart(period, convert_to_blocks_per_minute=True)

        # SLOW?
        chart, chart_name = await block_speed_chart(points, self.loc, normal_bpm=THOR_BLOCKS_PER_MINUTE,
                                                    time_scale_mode='time')
        last_block = block_notifier.last_thor_block
        last_block_ts = block_notifier.last_thor_block_update_ts

        recent_bps = await block_notifier.get_recent_blocks_per_second()
        state = await block_notifier.get_block_alert_state()

        d = now_ts() - last_block_ts if last_block_ts else 0

        # SLOW?
        await message.answer_photo(img_to_bio(chart, chart_name),
                                   caption=self.loc.text_block_time_report(last_block, d, recent_bps, state),
                                   disable_notification=True)

    async def show_top_pools(self, message: Message):
        await self.start_typing(message)

        notifier: BestPoolsNotifier = self.deps.best_pools_notifier
        if not (event := notifier.last_pool_detail):
            await message.answer(self.loc.TEXT_BEST_POOLS_NO_DATA, disable_notification=True)
            return

        text = self.loc.notification_text_best_pools(event, notifier.n_pools)
        generator = PoolPictureGenerator(self.loc, event)
        pic, pic_name = await generator.get_picture()
        await message.answer_photo(img_to_bio(pic, pic_name), caption=text, disable_notification=True)

    async def show_pol_state(self, message: Message):
        event = self.deps.pol_notifier.last_event
        if not event:
            await message.answer(self.loc.TEXT_POL_NO_DATA, disable_notification=True)
            return
        else:
            await message.answer(self.loc.notification_text_pol_stats(event), disable_notification=True)

    async def show_cex_flow(self, message: Message, period=DAY):
        notifier: RuneMoveNotifier = self.deps.rune_move_notifier
        flow = await notifier.tracker.read_within_period(period=period)
        flow.usd_per_rune = self.deps.price_holder.usd_per_rune
        text = self.loc.notification_text_cex_flow(flow)
        await message.answer(text, disable_notification=True)

    async def show_rune_supply(self, message: Message):
        await self.start_typing(message)

        market_fetcher: RuneMarketInfoFetcher = self.deps.rune_market_fetcher
        market_info = await market_fetcher.fetch()

        text = self.loc.text_metrics_supply(market_info)

        pic_gen = SupplyPictureGenerator(
            self.loc, market_info.supply_info, self.deps.net_stats, prev_supply=market_info.prev_supply_info
        )
        pic, pic_name = await pic_gen.get_picture()

        await message.answer_photo(img_to_bio(pic, pic_name), caption=text, disable_notification=True)

    async def show_dex_aggr(self, message: Message, period=DAY):
        await self.start_typing(message)

        report = await self.deps.dex_analytics.get_analytics(period)
        text = self.loc.notification_text_dex_report(report)
        await message.answer(text,
                             disable_web_page_preview=True,
                             disable_notification=True)

    async def show_pol(self, message: Message):
        await self.start_typing(message)

        report = self.deps.pol_notifier.last_event
        text = self.loc.notification_text_pol_stats(report)
        await message.answer(text,
                             disable_web_page_preview=True,
                             disable_notification=True)

    async def show_weekly_stats(self, message: Message):
        await self.start_typing(message)

        if not self.deps.weekly_stats_notifier or not self.deps.weekly_stats_notifier.last_event:
            await message.answer(self.loc.TEXT_WEEKLY_STATS_NO_DATA,
                                 disable_notification=True)
            return

        ev = self.deps.weekly_stats_notifier.last_event

        pic_gen = KeyStatsPictureGenerator(self.loc, ev)
        pic, pic_name = await pic_gen.get_picture()
        caption = self.loc.notification_text_key_metrics_caption(ev)

        await message.answer_photo(img_to_bio(pic, pic_name), caption=caption, disable_notification=True)

    async def show_lending_stats(self, message: Message):
        await self.start_typing(message)

        try:
            event = await self.deps.lend_stats_notifier.get_last_event()
        except AttributeError:
            event = None

        text = self.loc.notification_lending_stats(event) if event else self.loc.TEXT_LENDING_STATS_NO_DATA
        await message.answer(text, disable_notification=True)

    async def show_trade_acc_stats(self, message: Message):
        await self.start_typing(message)

        if not self.deps.tr_acc_summary_notifier:
            await message.answer("This method is disabled.", disable_notification=True)
            return

        event = self.deps.tr_acc_summary_notifier.last_event

        text = self.loc.notification_text_trade_account_summary(event) if event else self.loc.TEXT_WEEKLY_STATS_NO_DATA
        await message.answer(text, disable_notification=True)

    async def show_rune_burned(self, message: Message):
        await self.start_typing(message)

        notifier = BurnNotifier(self.deps)
        event = await notifier.get_event()
        if not event:
            await message.answer(self.loc.TEXT_BURN_NO_DATA, disable_notification=True)
            return

        text = self.loc.notification_rune_burn(event)
        photo, photo_name = await self.deps.alert_presenter.render_rune_burn_graph(self.loc, event)
        await message.answer_photo(img_to_bio(photo, photo_name), caption=text, disable_notification=True)

    # ---- Ask for duration (universal)

    def parse_duration_response(self, message: Message):
        if message.text == self.loc.BUTTON_1_HOUR:
            return HOUR
        elif message.text == self.loc.BUTTON_24_HOURS:
            return DAY
        elif message.text == self.loc.BUTTON_1_WEEK:
            return 7 * DAY
        elif message.text == self.loc.BUTTON_30_DAYS:
            return 30 * DAY
        elif message.text == self.loc.BUTTON_BACK:
            return  # back
        else:
            period = parse_timespan_to_seconds(message.text.strip())
            return period

    KEY_NEXT_ACTION = '_metrics_ask_next_action'
    KEY_BACK_SUBMENU = '_metrics_back_submenu'

    async def ask_generic_duration(self, message: Message, next_state, back_state):
        await message.answer(self.loc.TEXT_ASK_DURATION, reply_markup=kbd([
            [
                self.loc.BUTTON_1_HOUR,
                self.loc.BUTTON_24_HOURS,
                self.loc.BUTTON_1_WEEK,
                self.loc.BUTTON_30_DAYS,
            ],
            [
                self.loc.BUTTON_BACK
            ]
        ]))

        self.data[self.KEY_NEXT_ACTION] = next_state
        self.data[self.KEY_BACK_SUBMENU] = back_state

        await MetricsStates.GENERIC_DURATION.set()

    @message_handler(state=MetricsStates.GENERIC_DURATION)
    async def on_generic_duration_reply(self, message: Message):
        next_state = self.data.get(self.KEY_NEXT_ACTION, '')
        back_state = self.data.get(self.KEY_BACK_SUBMENU, '')

        period = self.parse_duration_response(message)
        if isinstance(period, str):
            # error
            await message.reply(period)
            return

        if not period:
            # go back
            if back_state == 'net_op':
                await self.show_menu_net_op(message)
            elif back_state == 'financial':
                await self.show_menu_financial(message)
            else:
                await self.show_main_menu(message)
            return

        # action
        if next_state == 'price':
            await self.show_price(message, period)
        elif next_state == 'queue':
            await self.show_queue(message, period)
        elif next_state == 'savers':
            await self.show_savers(message)
        elif next_state == 'cex_flow':
            await self.show_cex_flow(message, period)
        elif next_state == 'dex_aggr':
            await self.show_dex_aggr(message, period)
        elif next_state == 'block_time':
            await self.show_block_time(message, period)
        else:
            raise Exception(f'Unknown next state: "{next_state}"!')
