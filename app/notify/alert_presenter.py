import asyncio

from api.midgard.name_service import NameService, NameMap, add_thor_suffix
from api.w3.dex_analytics import DexReport
from comm.localization.manager import BaseLocalization
from comm.picture.achievement_picture import build_achievement_picture_generator
from comm.picture.block_height_picture import block_speed_chart
from comm.picture.nodes_pictures import NodePictureGenerator
from comm.picture.pools_picture import PoolPictureGenerator
from comm.picture.price_picture import price_graph_from_db
from comm.picture.queue_picture import queue_graph
from comm.picture.supply_picture import SupplyPictureGenerator
from jobs.achievement.ach_list import Achievement
from jobs.fetch.cached.last_block import EventLastBlock
from jobs.fetch.chain_id import AlertChainIdChange
from lib.constants import THOR_BLOCKS_PER_MINUTE, thor_to_float, THOR_BASIS_POINT_MAX, Chains
from lib.date_utils import DAY
from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.draw_utils import img_to_bio
from lib.html_renderer import InfographicRendererRPC
from lib.logs import WithLogger
from lib.texts import shorten_text_middle
from lib.utils import namedtuple_to_dict, recursive_asdict
from models.asset import Asset, is_ambiguous_asset
from models.cap_info import AlertLiquidityCap
from models.circ_supply import EventRuneBurn
from models.key_stats_model import AlertKeyStats
from models.last_block import EventBlockSpeed, BlockProduceState
from models.memo import THORMemo
from models.mimir import AlertMimirChange, AlertMimirVoting
from models.net_stats import AlertNetworkStats
from models.node_info import AlertNodeChurn
from models.pool_info import PoolChanges, EventPools
from models.price import AlertPrice, RuneMarketInfo, AlertPriceDiverge
from models.queue import AlertQueue
from models.ruji import AlertRujiraMergeStats
from models.runepool import AlertPOLState, AlertRunepoolStats
from models.runepool import AlertRunePoolAction
from models.s_swap import AlertSwapStart
from models.secured import AlertSecuredAssetSummary
from models.tcy import TcyFullInfo
from models.trade_acc import AlertTradeAccountAction, AlertTradeAccountStats
from models.transfer import RuneCEXFlow, NativeTokenTransfer
from models.tx import EventLargeTransaction
from models.version import AlertVersionUpgradeProgress, AlertVersionChanged
from notify.broadcast import Broadcaster
from notify.channel import BoardMessage
from notify.public.chain_notify import AlertChainHalt


class AlertPresenter(INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.broadcaster: Broadcaster = deps.broadcaster
        self.name_service: NameService = deps.name_service

        r_cfg = deps.cfg.infographic_renderer

        self.renderer = InfographicRendererRPC(
            deps,
            url=r_cfg.as_str('renderer_url', 'http://127.0.0.1:8404/render')
        )
        self.use_renderer = r_cfg.get_pure('use_html_renderer', False)
        if self.use_renderer:
            self.logger.info(f'Using renderer: {self.use_renderer}; URL is {self.renderer.url}')

    async def on_data(self, sender, data):
        # noinspection PyAsyncCall
        asyncio.create_task(self.handle_data(data))

    async def handle_data(self, data):
        if isinstance(data, RuneCEXFlow):
            await self._handle_rune_cex_flow(data)
        elif isinstance(data, NativeTokenTransfer):
            await self._handle_rune_transfer(data)
        elif isinstance(data, EventBlockSpeed):
            await self._handle_block_speed(data)
        elif isinstance(data, EventLargeTransaction):
            await self._handle_large_tx(data)
        elif isinstance(data, DexReport):
            await self._handle_dex_report(data)
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
        elif isinstance(data, AlertPrice):
            await self._handle_price(data)
        elif isinstance(data, AlertMimirChange):
            await self._handle_mimir(data)
        elif isinstance(data, AlertChainHalt):
            await self._handle_chain_halt(data)
        elif isinstance(data, EventPools):
            await self._handle_best_pools(data)
        elif isinstance(data, AlertTradeAccountAction):
            await self._handle_trade_account_move(data)
        elif isinstance(data, AlertTradeAccountStats):
            await self._handle_trade_account_summary(data)
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
        elif isinstance(data, AlertRujiraMergeStats):
            await self._handle_rujira_merge_stats(data)
        elif isinstance(data, AlertSecuredAssetSummary):
            await self._handle_secured_asset_summary(data)
        elif isinstance(data, TcyFullInfo):
            await self._handle_tcy_report(data)
        elif isinstance(data, AlertNetworkStats):
            await self._handle_net_stats(data)
        elif isinstance(data, EventLastBlock):
            pass  # currently no action
        else:
            self.logger.error(f'Unknown alert data type: {type(data)}')

    async def load_names(self, addresses) -> NameMap:
        if isinstance(addresses, str):
            addresses = (addresses,)

        return await self.name_service.safely_load_thornames_from_address_set(addresses)

    # ---- PARTICULARLY ----

    async def _handle_rune_transfer(self, transfer: NativeTokenTransfer):
        name_map = await self.load_names([
            transfer.from_addr, transfer.to_addr
        ])

        await self.broadcaster.broadcast_to_all(
            "public:rune_transfer",
            BaseLocalization.notification_text_rune_transfer_public,
            transfer, name_map)

    async def _handle_rune_cex_flow(self, flow: RuneCEXFlow):
        await self.broadcaster.broadcast_to_all(
            "public:rune_cex_flow",
            BaseLocalization.notification_text_cex_flow,
            flow)

    async def _handle_block_speed(self, event: EventBlockSpeed):
        async def _block_speed_picture_generator(loc: BaseLocalization, points, event):
            chart, chart_name = await block_speed_chart(points, loc,
                                                        normal_bpm=THOR_BLOCKS_PER_MINUTE,
                                                        time_scale_mode='time')

            if event.state in (BlockProduceState.StateStuck, BlockProduceState.Producing):
                caption = loc.notification_text_block_stuck(event)
            else:
                caption = loc.notification_text_block_pace(event)

            return BoardMessage.make_photo(chart, caption=caption, photo_file_name=chart_name)

        await self.broadcaster.broadcast_to_all(
            "public:block_speed",
            _block_speed_picture_generator, event.points,
            event
        )

    async def _handle_dex_report(self, event: DexReport):
        await self.broadcaster.broadcast_to_all(
            "public:dex_report",
            BaseLocalization.notification_text_dex_report,
            event
        )

    async def _handle_pool_churn(self, event: PoolChanges):
        await self.broadcaster.broadcast_to_all(
            "public:pool_churn",
            BaseLocalization.notification_text_pool_churn, event
        )

    async def _handle_achievement(self, event: Achievement):
        async def _gen(loc: BaseLocalization, _a: Achievement):
            pic_gen = build_achievement_picture_generator(_a, loc.ach)
            pic, pic_name = await pic_gen.get_picture()
            caption = loc.ach.notification_achievement_unlocked(event)
            return BoardMessage.make_photo(pic, caption=caption, photo_file_name=pic_name)

        await self.broadcaster.broadcast_to_all(
            "public:achievement",
            _gen, event
        )

    async def _handle_pol(self, event: AlertPOLState):
        await self.broadcaster.broadcast_to_all(
            "public:pol",
            BaseLocalization.notification_text_pol_stats, event
        )

    async def _handle_node_churn(self, event: AlertNodeChurn):
        if event.finished:
            await self.broadcaster.broadcast_to_all(
                "public:node_churn:finish",
                BaseLocalization.notification_text_node_churn_finish,
                event.changes)

            if event.with_picture:
                async def _gen(loc: BaseLocalization):
                    gen = NodePictureGenerator(event.network_info, event.bond_chart, loc)
                    # noinspection PyUnresolvedReferences
                    pic = await gen.generate()
                    bio_graph = img_to_bio(pic, gen.proper_name())
                    caption = loc.PIC_NODE_DIVERSITY_BY_PROVIDER_CAPTION
                    return BoardMessage.make_photo(bio_graph, caption)

                await self.broadcaster.broadcast_to_all(
                    "public:node_churn:finish:picture",
                    _gen)

        else:
            # started
            await self.broadcaster.broadcast_to_all(
                "public:node_churn:start",
                BaseLocalization.notification_churn_started,
                event.changes
            )

    async def render_key_stats(self, _: BaseLocalization, event: AlertKeyStats):
        parameters = recursive_asdict(event, add_properties=True, handle_datetime=True)
        photo = await self.renderer.render('weekly_stats.jinja2', parameters)
        photo_name = 'weekly_stats.png'
        return photo, photo_name

    async def _handle_key_stats(self, event: AlertKeyStats):
        # PICTURE
        async def _gen(loc: BaseLocalization, _a: AlertKeyStats):
            pic, pic_name = await self.render_key_stats(loc, event)
            caption = loc.notification_text_key_metrics_caption(event)
            return BoardMessage.make_photo(pic, caption=caption, photo_file_name=pic_name)

        await self.broadcaster.broadcast_to_all(
            "public:key_stats",
            _gen, event
        )

    # ----- swaps and other actions -----

    async def _handle_large_tx(self, tx_event: EventLargeTransaction):
        name_map = await self.load_names(tx_event.transaction.all_addresses)

        if tx_event.is_swap:
            # post a new infographic
            await self._handle_swap_finished(tx_event, name_map)
        else:
            # old style text notification
            await self.broadcaster.broadcast_to_all(
                "public:large_tx",
                BaseLocalization.notification_text_large_single_tx,
                tx_event, name_map
            )

    async def _handle_swap_finished(self, event: EventLargeTransaction, name_map: NameMap):
        async def message_gen(loc: BaseLocalization):
            text = loc.notification_text_large_single_tx(event, name_map)
            photo, photo_name = await self.render_swap_finish(loc, event, name_map)
            if photo is not None:
                return BoardMessage.make_photo(photo, text, photo_name)
            else:
                return text

        await self.deps.broadcaster.broadcast_to_all(
            "public:swap_finished",
            message_gen
        )

    @staticmethod
    def _gen_user_address_for_renderer(name_map, address):
        user_name_thor = name_map.by_address.get(address) if name_map else None
        if user_name_thor:
            return add_thor_suffix(user_name_thor)
        else:
            # just address
            return shorten_text_middle(address, 6, 4) if address else ''

    @staticmethod
    def _get_chain_logo(asset: Asset) -> str:
        if is_ambiguous_asset(asset):
            if asset.chain == Chains.BASE:
                return 'BASE'  # Base has ETH as gas asset, but we wanna display BASE.png here
            else:
                # other just use chain's gas asset as logo
                return str(Asset.gas_asset_from_chain(asset.chain))
        else:
            return ''  # no ambiguity

    def get_affiliates(self, memo: THORMemo):
        ns = self.deps.name_service
        return (
            [ns.get_affiliate_name(a.address) for a in memo.affiliates],
            [ns.get_affiliate_logo(a.address) for a in memo.affiliates],
        )

    async def render_swap_start(self, loc, data: AlertSwapStart, name_map: NameMap):
        if not self.use_renderer:
            return None, None

        user_name = self._gen_user_address_for_renderer(name_map, data.from_address)

        from_asset = Asset(data.in_asset)
        to_asset = Asset(data.out_asset)

        aff_fee_percent = data.memo.affiliate_fee_bp / THOR_BASIS_POINT_MAX * 100.0
        aff_names, aff_logos = self.get_affiliates(data.memo)

        parameters = {
            "user_name": user_name,
            "source_address": data.from_address,
            "tx_hash": data.tx_id,

            "source_asset": str(from_asset),
            "source_asset_logo": str(from_asset.l1_asset),
            "source_asset_name": from_asset.name,
            "source_chain_logo": self._get_chain_logo(from_asset),

            "destination_asset": str(to_asset),
            "destination_logo": str(to_asset.l1_asset),
            "destination_asset_name": to_asset.name,
            "destination_chain_logo": self._get_chain_logo(to_asset),

            "source_amount": data.in_amount_float,
            "destination_amount": thor_to_float(data.expected_out_amount),
            "volume_usd": data.volume_usd,

            "affiliate_names": aff_names,
            "affiliate_logos": aff_logos,
            "affiliate_fee": aff_fee_percent,

            "swap_quantity": data.quantity,
            "swap_interval": data.interval,
            "total_estimated_time_sec": data.expected_total_swap_sec,
        }
        photo = await self.renderer.render('swap_start.jinja2', parameters)
        photo_name = 'swap_start.png'
        return photo, photo_name

    async def render_swap_finish(self, loc, data: EventLargeTransaction, name_map: NameMap):
        if not self.use_renderer:
            return None, None

        tx = data.transaction
        from_user_name = self._gen_user_address_for_renderer(name_map, tx.sender_address)
        to_user_name = self._gen_user_address_for_renderer(name_map, tx.recipient_address)

        from_subtx = tx.in_tx[0]
        to_subtx = tx.recipients_output
        from_asset = Asset(from_subtx.first_asset)
        to_asset = Asset(to_subtx.first_asset)

        aff_fee_percent = tx.memo.affiliate_fee_bp / THOR_BASIS_POINT_MAX * 100.0
        aff_names, aff_logos = self.get_affiliates(tx.memo)

        duration = data.duration
        if not (0 < duration < 3 * DAY):
            self.logger.error(f'Invalid duration for swap: {tx.tx_hash}: {duration} sec.')
            duration = 0

        refund_rate = 0
        if tx.meta_swap and tx.meta_swap.streaming:
            refund_rate = 100.0 * (1.0 - tx.meta_swap.streaming.success_rate)

        parameters = {
            "tx_hash_in": tx.first_input_tx_hash,
            "source_user_name": from_user_name,
            "source_address": tx.sender_address,
            "source_amount": thor_to_float(from_subtx.first_amount),
            "source_asset": str(from_asset),
            "source_asset_logo": str(from_asset.l1_asset),
            "source_asset_name": from_asset.name,
            "source_chain_logo": self._get_chain_logo(from_asset),
            "source_volume_usd": data.usd_volume_input,

            "tx_hash_out": tx.recipients_output.tx_id,
            "destination_user_name": to_user_name,
            "destination_address": to_subtx.address,
            "destination_amount": thor_to_float(to_subtx.first_amount),
            "destination_asset": str(to_asset),
            "destination_logo": str(to_asset.l1_asset),
            "destination_asset_name": to_asset.name,
            "destination_chain_logo": self._get_chain_logo(to_asset),
            "destination_volume_usd": data.usd_volume_output,

            "liquidity_fee_percent": tx.liquidity_fee_percent,

            "affiliate_names": aff_names,
            "affiliate_logos": aff_logos,
            "affiliate_fee": aff_fee_percent,

            "streaming_count": tx.meta_swap.streaming.quantity if tx.meta_swap.streaming else 0,

            "total_time_sec": duration,

            "refund": refund_rate > 0 or tx.has_refund_output,
            "refund_rate": refund_rate,
        }
        photo = await self.renderer.render('swap_finished.jinja2', parameters)
        photo_name = 'swap_finished.png'
        return photo, photo_name

    async def _handle_streaming_swap_start(self, event: AlertSwapStart):
        name_map = await self.load_names((event.from_address, event.memo.first_affiliate))

        async def message_gen(loc: BaseLocalization):
            text = loc.notification_text_streaming_swap_started(event, name_map)
            photo, photo_name = await self.render_swap_start(loc, event, name_map)
            if photo is not None:
                return BoardMessage.make_photo(photo, text, photo_name)
            else:
                return text

        await self.deps.broadcaster.broadcast_to_all(
            "public:streaming_swap_start",
            message_gen)

    async def render_price_graph(self, loc: BaseLocalization, event: AlertPrice):
        parameters = recursive_asdict(event, add_properties=True)
        photo = await self.renderer.render('price.jinja2', parameters)
        photo_name = 'price.png'
        return photo, photo_name

    async def _handle_price(self, event: AlertPrice):
        async def price_graph_gen(loc: BaseLocalization):
            if self.use_renderer:
                graph, graph_name = await self.render_price_graph(loc, event)
            else:
                graph, graph_name = await price_graph_from_db(self.deps, loc, event.price_graph_period)
            caption = loc.notification_text_price_update(event)
            return BoardMessage.make_photo(graph, caption=caption, photo_file_name=graph_name)

        await self.broadcaster.broadcast_to_all(
            "public:rune_price",
            price_graph_gen)

    async def _handle_chain_halt(self, event: AlertChainHalt):
        await self.broadcaster.broadcast_to_all(
            "public:chain_halt",
            BaseLocalization.notification_text_trading_halted_multi,
            event.changed_chains
        )

    async def _handle_mimir(self, data: AlertMimirChange):
        await self.deps.broadcaster.broadcast_to_all(
            "public:mimir_change",
            BaseLocalization.notification_text_mimir_changed,
            data.changes,
            data.holder,
        )

    async def _handle_best_pools(self, data: EventPools):
        async def generate_pool_picture(loc: BaseLocalization, event: EventPools):
            pic_gen = PoolPictureGenerator(loc, event)
            pic, pic_name = await pic_gen.get_picture()
            caption = loc.notification_text_best_pools(event)
            return BoardMessage.make_photo(pic, caption=caption, photo_file_name=pic_name)

        await self.deps.broadcaster.broadcast_to_all(
            "public:best_pools",
            generate_pool_picture, data
        )

    async def _handle_trade_account_move(self, data: AlertTradeAccountAction):
        name_map = await self.load_names([data.actor, data.destination_address])
        await self.deps.broadcaster.broadcast_to_all(
            "public:trade_account:action",
            BaseLocalization.notification_text_trade_account_move,
            data,
            name_map
        )

    async def _handle_trade_account_summary(self, data: AlertTradeAccountStats):
        await self.deps.broadcaster.broadcast_to_all(
            "public:trade_account:summary",
            BaseLocalization.notification_text_trade_account_summary,
            data,
        )

    async def _handle_runepool_action(self, data: AlertRunePoolAction):
        name_map = await self.load_names([data.actor, data.destination_address])
        await self.deps.broadcaster.broadcast_to_all(
            "public:runepool:action",
            BaseLocalization.notification_runepool_action,
            data,
            name_map
        )

    async def _handle_runepool_stats(self, data: AlertRunepoolStats):
        await self.deps.broadcaster.broadcast_to_all(
            "public:runepool_stats",
            BaseLocalization.notification_runepool_stats, data
        )

    async def _handle_chain_id(self, data: AlertChainIdChange):
        await self.deps.broadcaster.broadcast_to_all(
            "public:chain_id_change",
            BaseLocalization.notification_text_chain_id_changed, data
        )

    async def _handle_supply(self, market_info: RuneMarketInfo):
        async def supply_pic_gen(loc: BaseLocalization):
            gen = SupplyPictureGenerator(
                loc, market_info.supply_info, self.deps.net_stats, market_info.prev_supply_info
            )
            pic, pic_name = await gen.get_picture()
            text = loc.text_metrics_supply(market_info)
            return BoardMessage.make_photo(pic, text, pic_name)

        await self.deps.broadcaster.broadcast_to_all(
            "public:rune_supply",
            supply_pic_gen
        )

    async def _handle_version_upgrade_progress(self, data: AlertVersionUpgradeProgress):
        await self.deps.broadcaster.broadcast_to_all(
            "public:version:progress",
            BaseLocalization.notification_text_version_changed_progress,
            data
        )

    async def _handle_version_changed(self, data: AlertVersionChanged):
        await self.deps.broadcaster.broadcast_to_all(
            "public:version:changed",
            BaseLocalization.notification_text_version_changed, data
        )

    async def _handle_mimir_voting(self, e: AlertMimirVoting):
        await self.deps.broadcaster.broadcast_to_all(
            "public:mimir:voting",
            BaseLocalization.notification_text_mimir_voting_progress, e)

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

        await self.deps.broadcaster.broadcast_to_all(
            "public:queue",
            message_gen)

    async def _handle_liquidity_cap(self, data: AlertLiquidityCap):
        f = BaseLocalization.notification_text_cap_full if data.is_full \
            else BaseLocalization.notification_text_cap_opened_up
        await self.deps.broadcaster.broadcast_to_all(
            "public:liquidity_cap",
            f, data.cap)

    async def _handle_price_divergence(self, data: AlertPriceDiverge):
        await self.deps.broadcaster.broadcast_to_all(
            "public:price_divergence",
            BaseLocalization.notification_text_price_divergence, data)

    async def render_rune_burn_graph(self, loc, data: EventRuneBurn):
        # todo: share EventRuneBurn between the components, use Pydantic
        photo = await self.renderer.render('rune_burn_and_income.jinja2', namedtuple_to_dict(data))
        photo_name = 'rune_burnt.png'
        return photo, photo_name

    async def _handle_rune_burn(self, data: EventRuneBurn):
        async def message_gen(loc: BaseLocalization):
            text = loc.notification_rune_burn(data)
            photo, photo_name = await self.render_rune_burn_graph(loc, data)
            if photo is not None:
                return BoardMessage.make_photo(photo, text, photo_name)
            else:
                return text

        await self.deps.broadcaster.broadcast_to_all(
            "public:rune_burn",
            message_gen)

    async def render_rujira_merge_graph(self, loc, data: AlertRujiraMergeStats):
        photo = await self.renderer.render('rujira_merge.jinja2', namedtuple_to_dict(data))
        return photo, 'rujira_merge.png'

    async def _handle_rujira_merge_stats(self, data: AlertRujiraMergeStats):
        names = await self.load_names(data.addresses)

        try:
            data.update_names(names)
        except Exception as e:
            self.logger.exception(f'Failed to load names for merge: {e}', stack_info=True)

        async def message_gen(loc: BaseLocalization):
            text = loc.notification_rujira_merge_stats(data)
            photo, photo_name = await self.render_rujira_merge_graph(loc, data)
            if photo is not None:
                return BoardMessage.make_photo(photo, text, photo_name)
            else:
                return text

        await self.deps.broadcaster.broadcast_to_all(
            "public:rujira:merge_stats",
            message_gen)

    async def render_secured_asset_summary(self, loc: BaseLocalization, data: AlertSecuredAssetSummary):
        photo = await self.renderer.render('secured_asset_summary.jinja2', {
            **namedtuple_to_dict(data),
        })
        photo_name = 'secured_asset_summary.png'
        return photo, photo_name

    async def _handle_secured_asset_summary(self, data: AlertSecuredAssetSummary):
        async def message_gen(loc: BaseLocalization):
            text = loc.notification_text_secured_asset_summary(data)
            photo, photo_name = await self.render_secured_asset_summary(loc, data)
            if photo is not None:
                return BoardMessage.make_photo(photo, text, photo_name)
            else:
                return text

        await self.deps.broadcaster.broadcast_to_all(
            "public:secured_asset:summary",
            message_gen)

    async def render_tcy_infographic(self, loc: BaseLocalization, data: TcyFullInfo):
        photo = await self.renderer.render('tcy_info.jinja2', data.model_dump())
        photo_name = 'tcy_info.png'
        return photo, photo_name

    async def _handle_tcy_report(self, data: TcyFullInfo):
        async def message_gen(loc: BaseLocalization):
            text = loc.notification_text_tcy_info_caption(data)
            photo, photo_name = await self.render_tcy_infographic(loc, data)
            if photo is not None:
                return BoardMessage.make_photo(photo, text, photo_name)
            else:
                return text

        await self.deps.broadcaster.broadcast_to_all(
            "public:tcy:summary",
            message_gen)

    async def _handle_net_stats(self, data: AlertNetworkStats):
        await self.deps.broadcaster.broadcast_to_all(
            "public:network_stats",
            BaseLocalization.notification_text_network_summary, data)
