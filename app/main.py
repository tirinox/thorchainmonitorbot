import asyncio

from api.aionode.connector import ThorConnector
from api.midgard.connector import MidgardConnector
from api.midgard.name_service import NameService
from api.w3.aggregator import AggregatorDataExtractor
from api.w3.dex_analytics import DexAnalyticsCollector
from comm.dialog.main import init_dialogs
from comm.discord.discord_bot import DiscordBot
from comm.localization.admin import AdminMessages
from comm.localization.manager import LocalizationManager
from comm.slack.slack_bot import SlackBot
from comm.telegram.sticker_downloader import TelegramStickerDownloader
from comm.telegram.telegram import TelegramBot
from comm.twitter.twitter_bot import TwitterBot, TwitterBotMock
from jobs.achievement.notifier import AchievementsNotifier
from jobs.fetch.account_number import AccountNumberFetcher
from jobs.fetch.cached.last_block import LastBlockCached, LastBlockEventGenerator
from jobs.fetch.cached.mimir import MimirCached
from jobs.fetch.cached.nodes import NodeCache
from jobs.fetch.cached.pool import PoolCache
from jobs.fetch.cached.swap_history import SwapHistoryFetcher
from jobs.fetch.cap import CapInfoFetcher
from jobs.fetch.chain_id import ChainIdFetcher
from jobs.fetch.chains import ChainStateFetcher
from jobs.fetch.fair_price import RuneMarketInfoFetcher
from jobs.fetch.key_stats import KeyStatsFetcher
from jobs.fetch.mimir import ConstMimirFetcher
from jobs.fetch.net_stats import NetworkStatisticsFetcher
from jobs.fetch.node_info import NodeInfoFetcher
from jobs.fetch.pol import RunePoolFetcher
from jobs.fetch.pool_price import PoolFetcher, PoolInfoFetcherMidgard
from jobs.fetch.queue import QueueFetcher
from jobs.fetch.ruji_merge import RujiMergeStatsFetcher
from jobs.fetch.secured_asset import SecuredAssetAssetFetcher
from jobs.fetch.tcy import TCYInfoFetcher
from jobs.fetch.trade_accounts import TradeAccountFetcher
from jobs.fetch.tx import TxFetcher
from jobs.node_churn import NodeChurnDetector
from jobs.price_recorder import PriceRecorder
from jobs.ruji_merge import RujiMergeTracker
from jobs.scanner.native_scan import BlockScanner
from jobs.scanner.runepool import RunePoolEventDecoder
from jobs.scanner.swap_extractor import SwapExtractorBlock
from jobs.scanner.swap_routes import SwapRouteRecorder
from jobs.scanner.trade_acc import TradeAccEventDecoder
from jobs.scanner.transfer_detector import RuneTransferDetector
from jobs.user_counter import UserCounterMiddleware
from jobs.volume_filler import VolumeFillerUpdater
from jobs.volume_recorder import VolumeRecorder, TxCountRecorder
from lib.config import Config, SubConfig
from lib.constants import HTTP_CLIENT_ID
from lib.date_utils import parse_timespan_to_seconds
from lib.db import DB
from lib.depcont import DepContainer
from lib.emergency import EmergencyReport
from lib.logs import WithLogger, setup_logs_from_config
from lib.money import DepthCurve
from lib.scheduler import Scheduler
from lib.settings_manager import SettingsManager, SettingsProcessorGeneralAlerts
from models.memo import ActionType
from models.mimir import MimirHolder
from models.mimir_naming import MIMIR_DICT_FILENAME
from models.node_watchers import AlertWatchers
from models.price import PriceHolder
from notify.alert_presenter import AlertPresenter
from notify.broadcast import Broadcaster
from notify.channel import BoardMessage
from notify.personal.balance import PersonalBalanceNotifier
from notify.personal.bond_provider import PersonalBondProviderNotifier
from notify.personal.personal_main import NodeChangePersonalNotifier
from notify.personal.price_divergence import PersonalPriceDivergenceNotifier, SettingsProcessorPriceDivergence
from notify.personal.scheduled import PersonalPeriodicNotificationService
from notify.public.best_pool_notify import BestPoolsNotifier
from notify.public.burn_notify import BurnNotifier
from notify.public.cap_notify import LiquidityCapNotifier
from notify.public.cex_flow import CEXFlowNotifier
from notify.public.chain_id_notify import ChainIdNotifier
from notify.public.chain_notify import TradingHaltedNotifier
from notify.public.dex_report_notify import DexReportNotifier
from notify.public.key_metrics_notify import KeyMetricsNotifier
from notify.public.mimir_notify import MimirChangedNotifier
from notify.public.node_churn_notify import NodeChurnNotifier
from notify.public.pol_notify import POLNotifier
from notify.public.pool_churn_notify import PoolChurnNotifier
from notify.public.price_div_notify import PriceDivergenceNotifier
from notify.public.price_notify import PriceNotifier
from notify.public.queue_notify import QueueNotifier, QueueStoreMetrics
from notify.public.ruji_merge_stats import RujiMergeStatsTxNotifier
from notify.public.runepool_notify import RunePoolTransactionNotifier, RunepoolStatsNotifier
from notify.public.s_swap_notify import StreamingSwapStartTxNotifier
from notify.public.secured_notify import SecureAssetSummaryNotifier
from notify.public.stats_notify import NetworkStatsNotifier
from notify.public.supply_notify import SupplyNotifier
from notify.public.tcy_notify import TcySummaryNotifier
from notify.public.trade_acc_notify import TradeAccTransactionNotifier, TradeAccSummaryNotifier
from notify.public.transfer_notify import RuneMoveNotifier
from notify.public.tx_notify import GenericTxNotifier, LiquidityTxNotifier, SwapTxNotifier, RefundTxNotifier
from notify.public.version_notify import VersionNotifier
from notify.public.voting_notify import VotingNotifier


class App(WithLogger):
    def __init__(self, log_level=None):
        super().__init__()
        d = self.deps = DepContainer()

        d.is_loading = True
        self._bg_task = None

        self._init_configuration(log_level)

        d.db = DB()

        d.node_info_fetcher = NodeInfoFetcher(d)

        d.mimir_const_fetcher = ConstMimirFetcher(d)
        d.mimir_const_holder = MimirHolder()
        d.mimir_const_holder.mimir_rules.load(MIMIR_DICT_FILENAME)
        d.mimir_const_fetcher.add_subscriber(d.mimir_const_holder)

        d.pool_fetcher = PoolFetcher(d)

        d.rune_market_fetcher = RuneMarketInfoFetcher(d)
        d.trade_acc_fetcher = TradeAccountFetcher(d)

        d.fetcher_chain_state = ChainStateFetcher(d)

        self._init_settings()
        self._init_messaging()

    def _init_configuration(self, log_level=None):
        d = self.deps
        d.cfg = Config()

        sentry_url = d.cfg.as_str('sentry.url')
        if sentry_url:
            import sentry_sdk
            sentry_sdk.init(
                dsn=sentry_url,
                traces_sample_rate=1.0
            )

        setup_logs_from_config(d.cfg)
        self.logger.info('-' * 100)
        self.logger.info(f'Starting THORChainMonitoringBot for "{d.cfg.network_id}".')
        self.logger.info(f"Log level: {log_level}")

        self.sleep_step = d.cfg.sleep_step

    def _init_settings(self):
        d = self.deps
        d.settings_manager = SettingsManager(d.db, d.cfg)
        d.alert_watcher = AlertWatchers(d.db)
        d.gen_alert_settings_proc = SettingsProcessorGeneralAlerts(d.db, d.alert_watcher)
        d.settings_manager.add_subscriber(d.gen_alert_settings_proc)
        d.settings_manager.add_subscriber(SettingsProcessorPriceDivergence(d.alert_watcher))

    def _init_messaging(self):
        d = self.deps
        self._admin_messages = AdminMessages(d)
        d.telegram_bot = TelegramBot(d.cfg, d.db, d.loop)
        d.emergency = EmergencyReport(d.cfg.first_admin_id, d.telegram_bot.bot)
        d.loc_man = LocalizationManager(d.cfg)
        d.loc_man.set_mimir_rules(d.mimir_const_holder.mimir_rules)
        d.broadcaster = Broadcaster(d)
        d.alert_presenter = AlertPresenter(d)
        init_dialogs(d)

    async def create_thor_node_connector(self, thor_env=None):
        d = self.deps

        thor_env = thor_env or d.cfg.get_thor_env_by_network_id()
        thor_env_backup = d.cfg.get_thor_env_by_network_id(backup=True)

        d.thor_connector = ThorConnector(thor_env, d.session, additional_envs=[
            thor_env_backup
        ])
        d.thor_connector.set_client_id_for_all(HTTP_CLIENT_ID)

        d.thor_connector_archive = ThorConnector(thor_env_backup, d.session)
        d.thor_connector_archive.set_client_id_for_all(HTTP_CLIENT_ID)

        cfg: SubConfig = d.cfg.get('thor.midgard')
        d.midgard_connector = MidgardConnector(
            d.session,
            int(cfg.get_pure('tries', 3)),
            public_url=thor_env.midgard_url
        )

        d.swap_history_cache = SwapHistoryFetcher(d.midgard_connector)
        d.last_block_cache = LastBlockCached(d.thor_connector)
        d.mimir_cache = MimirCached(d.thor_connector, d.last_block_cache)
        d.pool_cache = PoolCache(d)
        d.node_cache = NodeCache(d)

        d.name_service = NameService(d.db, d.cfg, d.midgard_connector, d.node_cache)
        d.alert_presenter.name_service = d.name_service
        d.loc_man.set_name_service(d.name_service)

    async def _some_sleep(self):
        sleep_interval = self.deps.cfg.as_float('sleep_before_start', 0)
        if sleep_interval > 0:
            self.logger.info(f'Sleeping before start for {sleep_interval:.1f} sec..')
            await asyncio.sleep(sleep_interval)

    async def _preloading(self):
        d = self.deps
        await self._some_sleep()

        self.logger.info('Loading procedure start.')

        sleep_step = self.sleep_step
        retry_after = sleep_step * 5
        while True:
            try:
                self.logger.info('Testing DB connection...')
                await self.deps.db.test_db_connection()

                # update pools for bootstrap (other components need them)
                self.logger.info('Loading last block...')
                block_no = await d.last_block_cache.get_thor_block()
                self.logger.info(f'THORNode block is {block_no}')
                assert block_no > 0
                await asyncio.sleep(sleep_step)

                self.logger.info('Loading pools...')
                current_pools: PriceHolder = await d.pool_cache.get()
                if not current_pools or not current_pools.pool_info_map:
                    raise Exception("No pool data at startup!")
                else:
                    self.logger.info(f'Loaded {len(current_pools.pool_info_map)} pools.')
                await asyncio.sleep(sleep_step)

                self.logger.info('Loading node info...')
                await d.node_info_fetcher.run_once()  # get nodes beforehand
                await asyncio.sleep(sleep_step)

                self.logger.info('Loading constants and mimir...')
                await d.mimir_const_fetcher.run_once()  # get constants beforehand
                await asyncio.sleep(sleep_step)

                break  # all is good. exit the loop
            except Exception as e:
                if not isinstance(e, ConnectionError):
                    self.logger.exception(e)
                retry_after = retry_after * 2
                self.logger.error(f'No luck. {e!r} Retrying in {retry_after} sec...')
                await asyncio.sleep(retry_after)

    async def _prepare_task_graph(self):
        d = self.deps

        # ----- MANDATORY TASKS -----

        fetcher_queue = QueueFetcher(d)
        store_queue = QueueStoreMetrics(d)
        fetcher_queue.add_subscriber(store_queue)

        tasks = [
            d.pool_fetcher,
            d.mimir_const_fetcher,
            fetcher_queue,
            d.emergency,
        ]

        # ----- OPTIONAL TASKS -----

        achievements_enabled = d.cfg.get('achievements.enabled', True)
        achievements = AchievementsNotifier(d)
        if achievements_enabled:
            achievements.add_subscriber(d.alert_presenter)

        if d.cfg.get('native_scanner.enabled', True):
            # The block scanner itself
            max_attempts = d.cfg.as_int('native_scanner.max_attempts_per_block', 5)
            d.block_scanner = BlockScanner(d, max_attempts=max_attempts)
            tasks.append(d.block_scanner)
            reserve_address = d.cfg.as_str('native_scanner.reserve_address')

            # Personal Rune transfer notifications
            transfer_decoder = RuneTransferDetector(reserve_address)
            d.block_scanner.add_subscriber(transfer_decoder)
            balance_notifier = PersonalBalanceNotifier(d)
            transfer_decoder.add_subscriber(balance_notifier)

            # Count unique users
            d.user_counter = UserCounterMiddleware(d)
            d.block_scanner.add_subscriber(d.user_counter)

            # fixme: enable this later
            # d.affiliate_recorder = AffiliateRecorder(d)
            # d.block_scanner.add_subscriber(d.affiliate_recorder)

            if d.cfg.get('token_transfer.enabled', True):
                d.rune_move_notifier = RuneMoveNotifier(d)
                d.rune_move_notifier.add_subscriber(d.alert_presenter)
                transfer_decoder.add_subscriber(d.rune_move_notifier)

            if d.cfg.get('token_transfer.flow_summary.enabled', True):
                cex_flow_notifier = CEXFlowNotifier(d)
                cex_flow_notifier.add_subscriber(d.alert_presenter)
                transfer_decoder.add_subscriber(cex_flow_notifier)

            if achievements_enabled:
                ev_gen = LastBlockEventGenerator(d.last_block_cache)
                d.block_scanner.add_subscriber(ev_gen)
                ev_gen.add_subscriber(d.alert_presenter)

        if d.cfg.get('tx.enabled', True):
            main_tx_types = [
                # ThorTxType.TYPE_SWAP,  # fixme: using the native block scanner
                ActionType.REFUND,
                ActionType.ADD_LIQUIDITY,
                ActionType.WITHDRAW,
            ]

            ignore_donates = d.cfg.get('tx.ignore_donates', True)
            if not ignore_donates:
                main_tx_types.append(ActionType.DONATE)

            # Uses Midgard as data source
            fetcher_tx = TxFetcher(d, tx_types=main_tx_types)

            aggregator = AggregatorDataExtractor(d)
            fetcher_tx.add_subscriber(aggregator)

            # Swaps come from the Block scanner through NativeActionExtractor
            if d.block_scanner:
                native_action_extractor = SwapExtractorBlock(d)
                d.block_scanner.add_subscriber(native_action_extractor)
                native_action_extractor.add_subscriber(aggregator)

            volume_filler = VolumeFillerUpdater(d)
            aggregator.add_subscriber(volume_filler)

            d.dex_analytics = DexAnalyticsCollector(d)
            volume_filler.add_subscriber(d.dex_analytics)

            d.volume_recorder = VolumeRecorder(d)
            volume_filler.add_subscriber(d.volume_recorder)

            d.tx_count_recorder = TxCountRecorder(d)
            volume_filler.add_subscriber(d.tx_count_recorder)

            # Swap route recorder
            d.route_recorder = SwapRouteRecorder(d.db)
            volume_filler.add_subscriber(d.route_recorder)

            if achievements_enabled:
                volume_filler.add_subscriber(achievements)

            if d.cfg.tx.dex_aggregator_update.get('enabled', True):
                dex_report_notifier = DexReportNotifier(d, d.dex_analytics)
                volume_filler.add_subscriber(dex_report_notifier)
                dex_report_notifier.add_subscriber(d.alert_presenter)

            curve_pts = d.cfg.get_pure('tx.curve', default=DepthCurve.DEFAULT_TX_VS_DEPTH_CURVE)
            curve = DepthCurve(curve_pts)

            if d.cfg.tx.liquidity.get('enabled', True):
                d.liquidity_notifier_tx = LiquidityTxNotifier(d, d.cfg.tx.liquidity, curve=curve)
                volume_filler.add_subscriber(d.liquidity_notifier_tx)
                d.liquidity_notifier_tx.add_subscriber(d.alert_presenter)

            if d.cfg.tx.donate.get('enabled', True):
                d.donate_notifier_tx = GenericTxNotifier(d, d.cfg.tx.donate, tx_types=(ActionType.DONATE,),
                                                         curve=curve)

                volume_filler.add_subscriber(d.donate_notifier_tx)
                d.donate_notifier_tx.add_subscriber(d.alert_presenter)

            if d.cfg.tx.swap.get('enabled', True):
                d.swap_notifier_tx = SwapTxNotifier(d, d.cfg.tx.swap, curve=curve)
                volume_filler.add_subscriber(d.swap_notifier_tx)
                d.swap_notifier_tx.add_subscriber(d.alert_presenter)

                if d.cfg.tx.swap.also_trigger_when.streaming_swap.get('notify_start', True):
                    stream_swap_notifier = StreamingSwapStartTxNotifier(d)
                    d.block_scanner.add_subscriber(stream_swap_notifier)
                    stream_swap_notifier.add_subscriber(d.alert_presenter)

            if d.cfg.tx.refund.get('enabled', True):
                d.refund_notifier_tx = RefundTxNotifier(d, d.cfg.tx.refund, curve=curve)

                volume_filler.add_subscriber(d.refund_notifier_tx)
                d.refund_notifier_tx.add_subscriber(d.alert_presenter)

            tasks.append(fetcher_tx)

        if d.cfg.get('cap.enabled', True):
            fetcher_cap = CapInfoFetcher(d)
            notifier_cap = LiquidityCapNotifier(d)
            fetcher_cap.add_subscriber(notifier_cap)
            notifier_cap.add_subscriber(d.alert_presenter)
            tasks.append(fetcher_cap)

        if d.cfg.get('queue.enabled', True):
            notifier_queue = QueueNotifier(d)
            store_queue.add_subscriber(notifier_queue)
            notifier_queue.add_subscriber(d.alert_presenter)

        if d.cfg.get('net_summary.enabled', True):
            fetcher_stats = NetworkStatisticsFetcher(d)
            tasks.append(fetcher_stats)

            notifier_stats = NetworkStatsNotifier(d)
            notifier_stats.add_subscriber(d.alert_presenter)
            fetcher_stats.add_subscriber(notifier_stats)

            if achievements_enabled:
                fetcher_stats.add_subscriber(achievements)

        if d.cfg.get('node_info.enabled', True):
            churn_detector = NodeChurnDetector(d)
            d.node_info_fetcher.add_subscriber(churn_detector)
            tasks.append(d.node_info_fetcher)

            notifier_nodes = NodeChurnNotifier(d)
            churn_detector.add_subscriber(notifier_nodes)
            notifier_nodes.add_subscriber(d.alert_presenter)

            if d.cfg.get('node_info.bond_tools.enabled', True):
                bond_provider_tools = PersonalBondProviderNotifier(d)
                bond_provider_tools.log_events = d.cfg.get('node_info.bond_tools.log_events')
                churn_detector.add_subscriber(bond_provider_tools)

            if achievements_enabled:
                churn_detector.add_subscriber(achievements)

            if d.cfg.get('node_info.version.enabled', True):
                notifier_version = VersionNotifier(d)
                churn_detector.add_subscriber(notifier_version)
                notifier_version.add_subscriber(d.alert_presenter)

            if d.cfg.get('node_op_tools.enabled', True):
                d.node_op_notifier = NodeChangePersonalNotifier(d)
                await d.node_op_notifier.prepare()

                churn_detector.add_subscriber(d.node_op_notifier)

        if d.cfg.get('price.enabled', True):
            tasks.append(d.rune_market_fetcher)

            price_rec = PriceRecorder(d.db)
            d.rune_market_fetcher.add_subscriber(price_rec)

            # handles RuneMarketInfo
            notifier_price = PriceNotifier(d)
            notifier_price.add_subscriber(d.alert_presenter)

            d.rune_market_fetcher.add_subscriber(notifier_price)

            if achievements_enabled:
                d.rune_market_fetcher.add_subscriber(achievements)

            if d.cfg.get('price.divergence.enabled', True):
                price_div_notifier = PriceDivergenceNotifier(d)
                d.rune_market_fetcher.add_subscriber(price_div_notifier)

            if d.cfg.get('price.divergence.personal.enabled', True):
                personal_price_div_notifier = PersonalPriceDivergenceNotifier(d)
                d.rune_market_fetcher.add_subscriber(personal_price_div_notifier)

        if d.cfg.get('pool_churn.enabled', True):
            notifier_pool_churn = PoolChurnNotifier(d)
            d.pool_fetcher.add_subscriber(notifier_pool_churn)
            notifier_pool_churn.add_subscriber(d.alert_presenter)

        if d.cfg.get('best_pools.enabled', True):
            # note: we don't use "pool_fetcher" here since PoolInfoFetcherMidgard gives richer info including APY
            period = parse_timespan_to_seconds(d.cfg.best_pools.fetch_period)
            mdg_pool_fetcher = PoolInfoFetcherMidgard(d, period)
            d.best_pools_notifier = BestPoolsNotifier(d)
            mdg_pool_fetcher.add_subscriber(d.best_pools_notifier)
            d.best_pools_notifier.add_subscriber(d.alert_presenter)
            tasks.append(mdg_pool_fetcher)

        if d.cfg.get('chain_halt_state.enabled', True):
            notifier_trade_halt = TradingHaltedNotifier(d)
            d.fetcher_chain_state.add_subscriber(notifier_trade_halt)
            notifier_trade_halt.add_subscriber(d.alert_presenter)
            tasks.append(d.fetcher_chain_state)

        if d.cfg.get('constants.mimir_change.enabled', True):
            notifier_mimir_change = MimirChangedNotifier(d)
            d.mimir_const_fetcher.add_subscriber(notifier_mimir_change)
            notifier_mimir_change.add_subscriber(d.alert_presenter)

        if d.cfg.get('constants.voting.enabled', True):
            voting_notifier = VotingNotifier(d)
            d.mimir_const_fetcher.add_subscriber(voting_notifier)
            voting_notifier.add_subscriber(d.alert_presenter)
            if achievements_enabled:
                d.mimir_const_fetcher.add_subscriber(achievements)

        if d.cfg.get('supply.enabled', True):
            supply_notifier = SupplyNotifier(d)
            d.rune_market_fetcher.add_subscriber(supply_notifier)
            if d.rune_market_fetcher not in tasks:
                tasks.append(d.rune_market_fetcher)
            supply_notifier.add_subscriber(d.alert_presenter)

            if d.cfg.get('supply.rune_burn.notification.enabled', True):
                burn_notifier = BurnNotifier(d)
                d.rune_market_fetcher.add_subscriber(burn_notifier)
                burn_notifier.add_subscriber(d.alert_presenter)

        if d.cfg.get('wallet_counter.enabled', True) and achievements_enabled:  # only used along with achievements
            wallet_counter = AccountNumberFetcher(d)
            tasks.append(wallet_counter)
            if achievements_enabled:
                wallet_counter.add_subscriber(achievements)

        if d.cfg.get('key_metrics.enabled', True):
            d.key_stat_fetcher = KeyStatsFetcher(d)
            tasks.append(d.key_stat_fetcher)
            if d.cfg.get('key_metrics.notification.enabled', False):
                d.weekly_stats_notifier = KeyMetricsNotifier(d)
                d.key_stat_fetcher.add_subscriber(d.weekly_stats_notifier)
                d.weekly_stats_notifier.add_subscriber(d.alert_presenter)
            if achievements_enabled:
                d.key_stat_fetcher.add_subscriber(achievements)

        if d.cfg.get('trade_accounts.enabled', True):
            # Trade account actions
            traed = TradeAccEventDecoder(d.pool_cache)
            d.block_scanner.add_subscriber(traed)

            traed.add_subscriber(d.volume_recorder)
            traed.add_subscriber(d.tx_count_recorder)

            tr_acc_not = TradeAccTransactionNotifier(d)
            traed.add_subscriber(tr_acc_not)
            tr_acc_not.add_subscriber(d.alert_presenter)

            traed.add_subscriber(achievements)

            if d.cfg.get('trade_accounts.summary.enabled', True):
                tasks.append(d.trade_acc_fetcher)

                d.tr_acc_summary_notifier = TradeAccSummaryNotifier(d)
                d.tr_acc_summary_notifier.add_subscriber(d.alert_presenter)
                d.trade_acc_fetcher.add_subscriber(d.tr_acc_summary_notifier)
                d.trade_acc_fetcher.add_subscriber(achievements)

        if d.cfg.get('runepool.actions.enabled', True):
            runepool_decoder = RunePoolEventDecoder(d.db, d.pool_cache)
            d.block_scanner.add_subscriber(runepool_decoder)

            runepool_decoder.add_subscriber(d.volume_recorder)
            runepool_decoder.add_subscriber(d.tx_count_recorder)

            runepool_not = RunePoolTransactionNotifier(d)
            runepool_decoder.add_subscriber(runepool_not)
            runepool_not.add_subscriber(d.alert_presenter)

            if achievements:
                runepool_decoder.add_subscriber(achievements)

        runepool_fetcher = RunePoolFetcher(d)
        need_runepool_data = False

        if d.cfg.get('runepool.summary.enabled', True):
            d.runepool_summary_notifier = RunepoolStatsNotifier(d)
            runepool_fetcher.add_subscriber(d.runepool_summary_notifier)
            d.runepool_summary_notifier.add_subscriber(d.alert_presenter)
            need_runepool_data = True

        if d.cfg.get('runepool.pol_summary.enabled', True):
            d.pol_notifier = POLNotifier(d)
            runepool_fetcher.add_subscriber(d.pol_notifier)
            d.pol_notifier.add_subscriber(d.alert_presenter)
            need_runepool_data = True

        if need_runepool_data:
            tasks.append(runepool_fetcher)
            if achievements_enabled:
                runepool_fetcher.add_subscriber(achievements)

        if d.cfg.get('chain_id.enabled', True):
            chain_id_job = ChainIdFetcher(d)
            tasks.append(chain_id_job)

            chain_id_notifier = ChainIdNotifier(d)
            chain_id_notifier.add_subscriber(d.alert_presenter)
            chain_id_job.add_subscriber(chain_id_notifier)

        if d.cfg.get('rujira.enabled', True):
            if d.cfg.get('rujira.merge.enabled', True):
                # Record Merge txs real-time
                ruji_merge_tracker = RujiMergeTracker(d)
                d.block_scanner.add_subscriber(ruji_merge_tracker)

                ruji_stats_fetcher = RujiMergeStatsFetcher(d)
                tasks.append(ruji_stats_fetcher)

                if d.cfg.get('rujira.merge.notification.enabled', True):
                    notifier_ruji_merge = RujiMergeStatsTxNotifier(d)
                    notifier_ruji_merge.add_subscriber(d.alert_presenter)
                    ruji_stats_fetcher.add_subscriber(notifier_ruji_merge)

        if d.cfg.get('secured_assets.enabled', True):
            secured_asset_fetcher = SecuredAssetAssetFetcher(d)
            tasks.append(secured_asset_fetcher)

            if d.cfg.get('secured_assets.summary.notification.enabled', True):
                d.secured_asset_notifier = SecureAssetSummaryNotifier(d)
                secured_asset_fetcher.add_subscriber(d.secured_asset_notifier)
                d.secured_asset_notifier.add_subscriber(d.alert_presenter)

        if d.cfg.get('tcy.enabled', True):
            tcy_info_fetcher = TCYInfoFetcher(d)
            tasks.append(tcy_info_fetcher)

            if d.cfg.get('tcy.summary.notification.enabled', True):
                d.tcy_summary_notifier = TcySummaryNotifier(d)
                tcy_info_fetcher.add_subscriber(d.tcy_summary_notifier)
                d.tcy_summary_notifier.add_subscriber(d.alert_presenter)

        # -------- SCHEDULER --------

        scheduler_cfg = d.cfg.get('personal.scheduler')
        if scheduler_cfg.get('enabled', True):
            poll_interval = parse_timespan_to_seconds(scheduler_cfg.get_pure('poll_interval', '1m'))
            d.scheduler = Scheduler(d.db.redis, 'PersonalLPReports', poll_interval)
            tasks.append(d.scheduler)

            personal_lp_notifier = PersonalPeriodicNotificationService(d)
            d.scheduler.add_subscriber(personal_lp_notifier)

        # ------- BOTS -------

        sticker_downloader = TelegramStickerDownloader(d.telegram_bot.dp)

        if d.cfg.get('discord.enabled', False):
            d.discord_bot = DiscordBot(d.cfg, sticker_downloader)
            d.discord_bot.start_in_background()

        if d.cfg.get('slack.enabled', False):
            d.slack_bot = SlackBot(d.cfg, d.db, d.settings_manager, sticker_downloader)
            d.slack_bot.start_in_background()

        if d.cfg.get('twitter.enabled', False):
            if d.cfg.get('twitter.is_mock', False):
                self.logger.warning('Using Twitter Mock bot! All Tweets will go only to the logs!')
                d.twitter_bot = TwitterBotMock(d.cfg)
            else:
                self.logger.info('Using real Twitter bot.')
                d.twitter_bot = TwitterBot(d.cfg)

            d.twitter_bot.emergency = d.emergency

        return tasks

    async def _print_curves(self):
        # print some information about threshold curves
        d = self.deps
        ph = await d.pool_cache.get()
        if d.refund_notifier_tx:
            d.refund_notifier_tx.dbg_evaluate_curve_for_pools(ph)
        if d.swap_notifier_tx:
            d.swap_notifier_tx.dbg_evaluate_curve_for_pools(ph)
        if d.liquidity_notifier_tx:
            d.liquidity_notifier_tx.dbg_evaluate_curve_for_pools(ph)
        if d.donate_notifier_tx:
            d.donate_notifier_tx.dbg_evaluate_curve_for_pools(ph)

    def die(self, code=-100):
        if self._bg_task:
            self._bg_task.cancel()
        exit(code)

    async def _run_background_jobs(self):
        tasks = []
        try:
            # noinspection PyAsyncCall
            asyncio.create_task(self.deps.data_controller.run_save_job(self.deps.db))

            await self.create_thor_node_connector()

            tasks = await self._prepare_task_graph()
            await self._preloading()

            self.deps.is_loading = False
        except Exception as e:
            self.logger.exception(f'Failed to prepare tasks: {e}')
            self.logger.error(f'Terminating in {self.sleep_step} sec...')
            await asyncio.sleep(self.sleep_step)
            self.die()

        self.logger.info(f'Ready! Starting background jobs in {self.sleep_step}...')
        await asyncio.sleep(self.sleep_step)

        # noinspection PyAsyncCall
        asyncio.create_task(self._debug_command())

        # start background jobs
        self.logger.info(f'Total tasks to run: {len(tasks)}')
        try:
            running_tasks = [task.run_in_background() for task in tasks]
            self.logger.info(f'Total tasks to running: {len(running_tasks)}')
        except Exception as e:
            self.logger.exception(f'{e!r}', exc_info=True)
            self.die()

    async def _debug_command(self):
        await self._print_curves()

        await self.deps.telegram_bot.send_message(
            self.deps.cfg.first_admin_id,
            BoardMessage(self._admin_messages.text_bot_restarted())
        )

    async def on_startup(self, _):
        d = self.deps
        d.make_http_session()  # it must be inside a coroutine!
        d.loop = asyncio.get_event_loop()
        self._bg_task = asyncio.create_task(self._run_background_jobs())

    async def on_shutdown(self, _):
        if self.deps.session:
            await self.deps.session.close()

    def run_bot(self):
        self.deps.telegram_bot.run(on_startup=self.on_startup, on_shutdown=self.on_shutdown)


if __name__ == '__main__':
    App().run_bot()
