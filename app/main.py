import asyncio
import logging
import os

from aionode.connector import ThorConnector
from localization.admin import AdminMessages
from localization.manager import LocalizationManager
from services.dialog.discord.discord_bot import DiscordBot
from services.dialog.main import init_dialogs
from services.dialog.slack.slack_bot import SlackBot
from services.dialog.telegram.sticker_downloader import TelegramStickerDownloader
from services.dialog.telegram.telegram import TelegramBot
from services.dialog.twitter.twitter_bot import TwitterBot, TwitterBotMock
from services.jobs.achievement.notifier import AchievementsNotifier
from services.jobs.fetch.account_number import AccountNumberFetcher
from services.jobs.fetch.cap import CapInfoFetcher
from services.jobs.fetch.chains import ChainStateFetcher
from services.jobs.fetch.const_mimir import ConstMimirFetcher
from services.jobs.fetch.fair_price import RuneMarketInfoFetcher
from services.jobs.fetch.gecko_price import fill_rune_price_from_gecko
from services.jobs.fetch.key_stats import KeyStatsFetcher
from services.jobs.fetch.last_block import LastBlockFetcher
from services.jobs.fetch.lending_stats import LendingStatsFetcher
from services.jobs.fetch.chain_id import ChainIdFetcher
from services.jobs.fetch.net_stats import NetworkStatisticsFetcher
from services.jobs.fetch.node_info import NodeInfoFetcher
from services.jobs.fetch.pol import RunePoolFetcher
from services.jobs.fetch.pool_price import PoolFetcher, PoolInfoFetcherMidgard
from services.jobs.fetch.profit_against_cex import StreamingSwapVsCexProfitCalculator
from services.jobs.fetch.queue import QueueFetcher
from services.jobs.fetch.savers_vnx import SaversStatsFetcher
from services.jobs.fetch.trade_accounts import TradeAccountFetcher
from services.jobs.fetch.tx import TxFetcher
from services.jobs.node_churn import NodeChurnDetector
from services.jobs.scanner.loan_extractor import LoanExtractorBlock
from services.jobs.scanner.native_scan import NativeScannerBlock
from services.jobs.scanner.runepool import RunePoolEventDecoder
from services.jobs.scanner.swap_extractor import SwapExtractorBlock
from services.jobs.scanner.swap_routes import SwapRouteRecorder
from services.jobs.scanner.trade_acc import TradeAccEventDecoder
from services.jobs.transfer_detector import RuneTransferDetectorTxLogs
from services.jobs.user_counter import UserCounterMiddleware
from services.jobs.volume_filler import VolumeFillerUpdater
from services.jobs.volume_recorder import VolumeRecorder, TxCountRecorder
from services.lib.config import Config, SubConfig
from services.lib.constants import HTTP_CLIENT_ID
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.lib.emergency import EmergencyReport
from services.lib.logs import WithLogger
from services.lib.midgard.connector import MidgardConnector
from services.lib.midgard.name_service import NameService
from services.lib.money import DepthCurve
from services.lib.scheduler import Scheduler
from services.lib.settings_manager import SettingsManager, SettingsProcessorGeneralAlerts
from services.lib.utils import setup_logs
from services.lib.w3.aggregator import AggregatorDataExtractor
from services.lib.w3.dex_analytics import DexAnalyticsCollector
from services.models.memo import ActionType
from services.models.mimir import MimirHolder
from services.models.mimir_naming import MIMIR_DICT_FILENAME
from services.models.node_watchers import AlertWatchers
from services.notify.alert_presenter import AlertPresenter
from services.notify.broadcast import Broadcaster
from services.notify.channel import BoardMessage
from services.notify.personal.balance import PersonalBalanceNotifier
from services.notify.personal.bond_provider import PersonalBondProviderNotifier
from services.notify.personal.personal_main import NodeChangePersonalNotifier
from services.notify.personal.price_divergence import PersonalPriceDivergenceNotifier, SettingsProcessorPriceDivergence
from services.notify.personal.scheduled import PersonalPeriodicNotificationService
from services.notify.types.best_pool_notify import BestPoolsNotifier
from services.notify.types.block_notify import BlockHeightNotifier, LastBlockStore
from services.notify.types.cap_notify import LiquidityCapNotifier
from services.notify.types.chain_id_notify import ChainIdNotifier
from services.notify.types.chain_notify import TradingHaltedNotifier
from services.notify.types.dex_report_notify import DexReportNotifier
from services.notify.types.key_metrics_notify import KeyMetricsNotifier
from services.notify.types.lend_stats_notify import LendingStatsNotifier
from services.notify.types.lending_open_up import LendingCapsNotifier
from services.notify.types.loans_notify import LoanTxNotifier
from services.notify.types.mimir_notify import MimirChangedNotifier
from services.notify.types.node_churn_notify import NodeChurnNotifier
from services.notify.types.pol_notify import POLNotifier
from services.notify.types.pool_churn_notify import PoolChurnNotifier
from services.notify.types.price_div_notify import PriceDivergenceNotifier
from services.notify.types.price_notify import PriceNotifier
from services.notify.types.queue_notify import QueueNotifier, QueueStoreMetrics
from services.notify.types.runepool_notify import RunePoolTransactionNotifier, RunepoolStatsNotifier
from services.notify.types.s_swap_notify import StreamingSwapStartTxNotifier
from services.notify.types.savers_stats_notify import SaversStatsNotifier
from services.notify.types.stats_notify import NetworkStatsNotifier
from services.notify.types.supply_notify import SupplyNotifier
from services.notify.types.trade_acc_notify import TradeAccTransactionNotifier, TradeAccSummaryNotifier
from services.notify.types.transfer_notify import RuneMoveNotifier
from services.notify.types.tx_notify import GenericTxNotifier, LiquidityTxNotifier, SwapTxNotifier, RefundTxNotifier
from services.notify.types.version_notify import VersionNotifier
from services.notify.types.voting_notify import VotingNotifier


class App(WithLogger):
    def __init__(self, log_level=None):
        super().__init__()
        d = self.deps = DepContainer()

        d.is_loading = True
        self._bg_task = None

        self._admin_messages = AdminMessages(d)

        self._init_configuration(log_level)

        d.node_info_fetcher = NodeInfoFetcher(d)

        d.mimir_const_fetcher = ConstMimirFetcher(d)
        d.mimir_const_holder = MimirHolder()
        d.mimir_const_holder.mimir_rules.load(MIMIR_DICT_FILENAME)

        d.pool_fetcher = PoolFetcher(d)
        d.last_block_fetcher = LastBlockFetcher(d)
        d.last_block_store = LastBlockStore(d)
        d.last_block_fetcher.add_subscriber(d.last_block_store)
        d.rune_market_fetcher = RuneMarketInfoFetcher(d)
        d.trade_acc_fetcher = TradeAccountFetcher(d)

        self._init_settings()
        self._init_messaging()

        self.swap_notifier_tx = None
        self.refund_notifier_tx = None
        self.liquidity_notifier_tx = None
        self.donate_notifier_tx = None

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

        log_level = log_level or d.cfg.get_pure('log_level', logging.INFO)
        colorful_logs = d.cfg.get('colorful_logs', False)
        setup_logs(log_level, colorful=colorful_logs)
        self.logger.info('-' * 100)
        self.logger.info(f"Log level: {log_level}")

        # todo: ART logo
        self.logger.info(f'Starting THORChainMonitoringBot for "{d.cfg.network_id}".')

        d.loop = asyncio.get_event_loop()
        d.db = DB(d.loop)
        d.price_holder.load_stable_coins(d.cfg)

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

        d.name_service = NameService(d.db, d.cfg, d.midgard_connector, d.node_holder)
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

        if 'REPLACE_RUNE_TIMESERIES_WITH_GECKOS' in os.environ:
            await fill_rune_price_from_gecko(d.db)

        self.logger.info('Loading procedure start.')

        sleep_step = self.sleep_step
        retry_after = sleep_step * 5
        while True:
            try:
                self.logger.info('Testing DB connection...')
                await self.deps.db.test_db_connection()

                await self.create_thor_node_connector()

                # update pools for bootstrap (other components need them)
                self.logger.info('Loading last block...')
                await d.last_block_fetcher.run_once()
                await asyncio.sleep(sleep_step)

                self.logger.info('Loading pools...')
                current_pools = await d.pool_fetcher.reload_global_pools()
                if not current_pools:
                    raise Exception("No pool data at startup!")
                await asyncio.sleep(sleep_step)

                self.logger.info('Loading node info...')
                await d.node_info_fetcher.run_once()  # get nodes beforehand
                await asyncio.sleep(sleep_step)

                self.logger.info('Loading constants and mimir...')
                await d.mimir_const_fetcher.run_once()  # get constants beforehand
                await asyncio.sleep(sleep_step)

                # print some information about threshold curves
                if self.refund_notifier_tx:
                    self.refund_notifier_tx.dbg_evaluate_curve_for_pools()
                if self.swap_notifier_tx:
                    self.swap_notifier_tx.dbg_evaluate_curve_for_pools()
                if self.liquidity_notifier_tx:
                    self.liquidity_notifier_tx.dbg_evaluate_curve_for_pools()
                if self.donate_notifier_tx:
                    self.donate_notifier_tx.dbg_evaluate_curve_for_pools()

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
            d.last_block_fetcher,
            fetcher_queue,
            d.emergency,
        ]

        # ----- OPTIONAL TASKS -----

        achievements_enabled = d.cfg.get('achievements.enabled', True)
        achievements = AchievementsNotifier(d)
        if achievements_enabled:
            achievements.add_subscriber(d.alert_presenter)

            # achievements will subscribe to other components later in this method
            d.last_block_store.add_subscriber(achievements)

        if d.cfg.get('native_scanner.enabled', True):
            # The block scanner itself
            max_attempts = d.cfg.as_int('native_scanner.max_attempts_per_block', 5)
            d.block_scanner = NativeScannerBlock(d, max_attempts=max_attempts)
            tasks.append(d.block_scanner)
            reserve_address = d.cfg.as_str('native_scanner.reserve_address')

            # Personal Rune transfer notifications
            transfer_decoder = RuneTransferDetectorTxLogs(reserve_address)
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

            profit_calc = StreamingSwapVsCexProfitCalculator(d)
            volume_filler.add_subscriber(profit_calc)

            d.dex_analytics = DexAnalyticsCollector(d)
            profit_calc.add_subscriber(d.dex_analytics)

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
                self.liquidity_notifier_tx = LiquidityTxNotifier(d, d.cfg.tx.liquidity, curve=curve)
                volume_filler.add_subscriber(self.liquidity_notifier_tx)
                self.liquidity_notifier_tx.add_subscriber(d.alert_presenter)

            if d.cfg.tx.donate.get('enabled', True):
                self.donate_notifier_tx = GenericTxNotifier(d, d.cfg.tx.donate, tx_types=(ActionType.DONATE,),
                                                            curve=curve)

                volume_filler.add_subscriber(self.donate_notifier_tx)
                self.donate_notifier_tx.add_subscriber(d.alert_presenter)

            if d.cfg.tx.swap.get('enabled', True):
                self.swap_notifier_tx = SwapTxNotifier(d, d.cfg.tx.swap, curve=curve)
                volume_filler.add_subscriber(self.swap_notifier_tx)
                self.swap_notifier_tx.add_subscriber(d.alert_presenter)

                if d.cfg.tx.swap.also_trigger_when.streaming_swap.get('notify_start', True):
                    stream_swap_notifier = StreamingSwapStartTxNotifier(d)
                    d.block_scanner.add_subscriber(stream_swap_notifier)
                    stream_swap_notifier.add_subscriber(d.alert_presenter)

            if d.cfg.tx.refund.get('enabled', True):
                self.refund_notifier_tx = RefundTxNotifier(d, d.cfg.tx.refund, curve=curve)

                volume_filler.add_subscriber(self.refund_notifier_tx)
                self.refund_notifier_tx.add_subscriber(d.alert_presenter)

            if d.cfg.tx.loans.get('enabled', True):
                loan_extractor = LoanExtractorBlock(d)
                d.block_scanner.add_subscriber(loan_extractor)

                if achievements_enabled:
                    loan_extractor.add_subscriber(achievements)

                loan_notifier = LoanTxNotifier(d, curve=curve)
                loan_extractor.add_subscriber(loan_notifier)
                loan_notifier.add_subscriber(d.alert_presenter)

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

        if d.cfg.get('last_block.enabled', True):
            d.block_notifier = BlockHeightNotifier(d)
            d.last_block_store.add_subscriber(d.block_notifier)
            d.block_notifier.add_subscriber(d.alert_presenter)

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
            # handles RuneMarketInfo
            notifier_price = PriceNotifier(d)
            d.pool_fetcher.add_subscriber(notifier_price)
            notifier_price.add_subscriber(d.alert_presenter)

            if achievements_enabled:
                d.pool_fetcher.add_subscriber(achievements)

            if d.cfg.get('price.divergence.enabled', True):
                price_div_notifier = PriceDivergenceNotifier(d)
                d.pool_fetcher.add_subscriber(price_div_notifier)

            if d.cfg.get('price.divergence.personal.enabled', True):
                personal_price_div_notifier = PersonalPriceDivergenceNotifier(d)
                d.pool_fetcher.add_subscriber(personal_price_div_notifier)

        if d.cfg.get('pool_churn.enabled', True):
            notifier_pool_churn = PoolChurnNotifier(d)
            d.pool_fetcher.add_subscriber(notifier_pool_churn)
            notifier_pool_churn.add_subscriber(d.alert_presenter)

        if d.cfg.get('best_pools.enabled', True):
            # note: we don't use "pool_fetcher" here since PoolInfoFetcherMidgard gives richer info including APY
            period = parse_timespan_to_seconds(d.cfg.best_pools.fetch_period)
            fetcher_pool_info = PoolInfoFetcherMidgard(d, period)
            d.best_pools_notifier = BestPoolsNotifier(d)
            fetcher_pool_info.add_subscriber(d.best_pools_notifier)
            d.best_pools_notifier.add_subscriber(d.alert_presenter)
            tasks.append(fetcher_pool_info)

        if d.cfg.get('chain_halt_state.enabled', True):
            fetcher_chain_state = ChainStateFetcher(d)
            notifier_trade_halt = TradingHaltedNotifier(d)
            fetcher_chain_state.add_subscriber(notifier_trade_halt)
            notifier_trade_halt.add_subscriber(d.alert_presenter)
            tasks.append(fetcher_chain_state)

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
            d.pool_fetcher.add_subscriber(supply_notifier)
            supply_notifier.add_subscriber(d.alert_presenter)

        if d.cfg.get('saver_stats.enabled', True):
            d.saver_stats_fetcher = SaversStatsFetcher(d)
            tasks.append(d.saver_stats_fetcher)

            ssc = SaversStatsNotifier(d)
            ssc.add_subscriber(d.alert_presenter)

            if achievements_enabled:
                d.saver_stats_fetcher.add_subscriber(achievements)

        if d.cfg.get('wallet_counter.enabled', True) and achievements_enabled:  # only used along with achievements
            wallet_counter = AccountNumberFetcher(d)
            tasks.append(wallet_counter)
            if achievements_enabled:
                wallet_counter.add_subscriber(achievements)

        if d.cfg.get('key_metrics.enabled', True):
            metrics_fetcher = KeyStatsFetcher(d)
            tasks.append(metrics_fetcher)
            d.weekly_stats_notifier = metrics_notifier = KeyMetricsNotifier(d)
            metrics_fetcher.add_subscriber(metrics_notifier)
            metrics_notifier.add_subscriber(d.alert_presenter)
            if achievements_enabled:
                metrics_fetcher.add_subscriber(achievements)

        lending_report_enabled = d.cfg.get('lending.stats_report.enabled', True)
        lending_caps_alert_enabled = d.cfg.get('lending.caps_alert.enabled', True)
        if lending_caps_alert_enabled or lending_report_enabled:
            d.lend_stats_fetcher = LendingStatsFetcher(d)
            tasks.append(d.lend_stats_fetcher)

            if lending_report_enabled:
                d.lend_stats_notifier = LendingStatsNotifier(d)
                d.lend_stats_notifier.add_subscriber(d.alert_presenter)
                d.lend_stats_fetcher.add_subscriber(d.lend_stats_notifier)

            if lending_caps_alert_enabled:
                lend_cap_notifier = LendingCapsNotifier(d)
                lend_cap_notifier.add_subscriber(d.alert_presenter)
                d.lend_stats_fetcher.add_subscriber(lend_cap_notifier)

            if achievements_enabled:
                d.lend_stats_fetcher.add_subscriber(achievements)

        if d.cfg.get('trade_accounts.enabled', True):
            # Trade account actions
            traed = TradeAccEventDecoder(d.db, d.price_holder)
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
            runepool_decoder = RunePoolEventDecoder(d.db, d.price_holder)
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

    def die(self, code=-100):
        if self._bg_task:
            self._bg_task.cancel()
        exit(code)

    async def _run_background_jobs(self):
        tasks = []
        try:
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

        # todo: debug
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
        # await asyncio.gather(*(task.run() for task in tasks))

    async def _debug_command(self):
        await self.deps.telegram_bot.send_message(
            self.deps.cfg.first_admin_id,
            BoardMessage(self._admin_messages.text_bot_restarted())
        )

    async def on_startup(self, _):
        self.deps.make_http_session()  # it must be inside a coroutine!

        self._bg_task = asyncio.create_task(self._run_background_jobs())

    async def on_shutdown(self, _):
        if self.deps.session:
            await self.deps.session.close()

    def run_bot(self):
        self.deps.telegram_bot.run(on_startup=self.on_startup, on_shutdown=self.on_shutdown)


if __name__ == '__main__':
    App().run_bot()
