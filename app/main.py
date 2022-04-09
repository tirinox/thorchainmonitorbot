import asyncio
import logging
import os

import aiohttp
import ujson
from aiogram import Bot, Dispatcher, executor
from aiogram.types import *
from aiohttp import ClientTimeout
from aiothornode.connector import ThorConnector

from localization import LocalizationManager
from services.dialog import init_dialogs
from services.dialog.discord.discord_bot import DiscordBot
from services.dialog.slack.slack_bot import SlackBot
from services.jobs.fetch.bep2_move import BinanceOrgDexWSSClient
from services.jobs.fetch.cap import CapInfoFetcher
from services.jobs.fetch.chains import ChainStateFetcher
from services.jobs.fetch.const_mimir import ConstMimirFetcher
from services.jobs.fetch.fair_price import RuneMarketInfoFetcher
from services.jobs.fetch.gecko_price import fill_rune_price_from_gecko
from services.jobs.fetch.last_block import LastBlockFetcher
from services.jobs.fetch.net_stats import NetworkStatisticsFetcher
from services.jobs.fetch.node_info import NodeInfoFetcher
from services.jobs.fetch.pool_price import PoolPriceFetcher, PoolInfoFetcherMidgard
from services.jobs.fetch.queue import QueueFetcher
from services.jobs.fetch.tx import TxFetcher
from services.jobs.ilp_summer import ILPSummer
from services.jobs.node_churn import NodeChurnDetector
from services.jobs.volume_filler import VolumeFillerUpdater
from services.lib.config import Config, SubConfig
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.lib.midgard.connector import MidgardConnector
from services.lib.utils import setup_logs
from services.models.mimir import MimirHolder
from services.models.price import LastPriceHolder
from services.models.tx import ThorTxType
from services.notify.broadcast import Broadcaster
from services.notify.personal.personal_main import NodeChangePersonalNotifier
from services.notify.types.bep2_notify import BEP2MoveNotifier
from services.notify.types.best_pool_notify import BestPoolsNotifier
from services.notify.types.block_notify import BlockHeightNotifier
from services.notify.types.cap_notify import LiquidityCapNotifier
from services.notify.types.chain_notify import TradingHaltedNotifier
from services.notify.types.mimir_notify import MimirChangedNotifier
from services.notify.types.node_churn_notify import NodeChurnNotifier
from services.notify.types.pool_churn import PoolChurnNotifier
from services.notify.types.price_div_notify import PriceDivergenceNotifier
from services.notify.types.price_notify import PriceNotifier
from services.notify.types.queue_notify import QueueNotifier
from services.notify.types.stats_notify import NetworkStatsNotifier
from services.notify.types.tx_notify import GenericTxNotifier, SwitchTxNotifier
from services.notify.types.version_notify import VersionNotifier
from services.notify.types.voting_notify import VotingNotifier


class App:
    def __init__(self):
        d = self.deps = DepContainer()
        d.cfg = Config()

        log_level = d.cfg.get_pure('log_level', logging.INFO)
        setup_logs(log_level)

        logging.info(f'Starting THORChainMonitoringBot for "{d.cfg.network_id}".')

        d.price_holder.load_stable_coins(d.cfg)

        d.loop = asyncio.get_event_loop()
        d.db = DB(d.loop)

        d.is_loading = True

        d.price_holder = LastPriceHolder()

    def create_bot_stuff(self):
        d = self.deps

        d.bot = Bot(token=d.cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
        d.dp = Dispatcher(d.bot, loop=d.loop)
        d.loc_man = LocalizationManager(d.cfg)
        d.broadcaster = Broadcaster(d)

        init_dialogs(d)

    async def connect_chat_storage(self):
        if self.deps.dp:
            self.deps.dp.storage = await self.deps.db.get_storage()

    async def create_thor_node_connector(self):
        d = self.deps
        d.thor_connector = ThorConnector(d.cfg.get_thor_env_by_network_id(), d.session)
        await d.thor_connector.update_nodes()

        cfg: SubConfig = d.cfg.get('thor.midgard')

        d.midgard_connector = MidgardConnector(
            d.session,
            d.thor_connector,
            int(cfg.get_pure('tries', 3)),
            public_url=d.thor_connector.env.midgard_url,
            use_nodes=bool(cfg.get('use_nodes', True))
        )
        d.rune_market_fetcher = RuneMarketInfoFetcher(d)

    async def _some_sleep(self):
        sleep_interval = self.deps.cfg.as_float('sleep_before_start', 0)
        if sleep_interval > 0:
            logging.info(f'Sleeping before start for {sleep_interval:.1f} sec..')
            await asyncio.sleep(sleep_interval)

    async def _run_background_jobs(self):
        d = self.deps

        await self._some_sleep()

        if 'REPLACE_RUNE_TIMESERIES_WITH_GECKOS' in os.environ:
            await fill_rune_price_from_gecko(d.db)

        d.price_pool_fetcher = PoolPriceFetcher(d)

        # update pools for bootstrap (other components need them)
        current_pools = await d.price_pool_fetcher.reload_global_pools()
        if not current_pools:
            logging.error("No pool data at startup! Halt it!")
            exit(-1)

        fetcher_nodes = NodeInfoFetcher(d)
        d.node_info_fetcher = fetcher_nodes
        await fetcher_nodes.fetch()  # get nodes beforehand

        # mimir uses nodes! so it goes after fetcher_nodes
        fetcher_mimir = ConstMimirFetcher(d)
        self.deps.mimir_const_fetcher = fetcher_mimir
        self.deps.mimir_const_holder = MimirHolder()
        await fetcher_mimir.fetch()  # get constants beforehand

        tasks = [
            # mandatory tasks:
            d.price_pool_fetcher,
            fetcher_mimir
        ]

        if d.cfg.get('tx.enabled', True):
            fetcher_tx = TxFetcher(d)

            volume_filler = VolumeFillerUpdater(d)
            fetcher_tx.subscribe(volume_filler)

            if d.cfg.tx.liquidity.get('enabled', True):
                liq_notifier_tx = GenericTxNotifier(d, d.cfg.tx.liquidity,
                                                    tx_types=(ThorTxType.TYPE_ADD_LIQUIDITY, ThorTxType.TYPE_WITHDRAW))
                volume_filler.subscribe(liq_notifier_tx)

            if d.cfg.tx.donate.get('enabled', True):
                donate_notifier_tx = GenericTxNotifier(d, d.cfg.tx.donate, tx_types=(ThorTxType.TYPE_DONATE,))
                volume_filler.subscribe(donate_notifier_tx)

            if d.cfg.tx.swap.get('enabled', True):
                swap_notifier_tx = GenericTxNotifier(d, d.cfg.tx.swap, tx_types=(ThorTxType.TYPE_SWAP,))
                volume_filler.subscribe(swap_notifier_tx)

            if d.cfg.tx.refund.get('enabled', True):
                refund_notifier_tx = GenericTxNotifier(d, d.cfg.tx.refund, tx_types=(ThorTxType.TYPE_REFUND,))
                volume_filler.subscribe(refund_notifier_tx)

            if d.cfg.tx.switch.get('enabled', True):
                switch_notifier_tx = SwitchTxNotifier(d, d.cfg.tx.switch, tx_types=(ThorTxType.TYPE_SWITCH,))
                volume_filler.subscribe(switch_notifier_tx)

            # for tracking 24h ILP payouts
            ilp_summer = ILPSummer(d)
            fetcher_tx.subscribe(ilp_summer)

            tasks.append(fetcher_tx)

        if d.cfg.get('cap.enabled', True):
            fetcher_cap = CapInfoFetcher(d)
            notifier_cap = LiquidityCapNotifier(d)
            fetcher_cap.subscribe(notifier_cap)
            tasks.append(fetcher_cap)

        if d.cfg.get('queue.enabled', True):
            fetcher_queue = QueueFetcher(d)
            notifier_queue = QueueNotifier(d)
            fetcher_queue.subscribe(notifier_queue)
            tasks.append(fetcher_queue)

        if d.cfg.get('net_summary.enabled', True):
            fetcher_stats = NetworkStatisticsFetcher(d)
            notifier_stats = NetworkStatsNotifier(d)
            fetcher_stats.subscribe(notifier_stats)
            tasks.append(fetcher_stats)

        if d.cfg.get('last_block.enabled', True):
            fetcher_last_block = LastBlockFetcher(d)
            last_block_notifier = BlockHeightNotifier(d)
            fetcher_last_block.subscribe(last_block_notifier)
            d.block_notifier = last_block_notifier
            tasks.append(fetcher_last_block)

        if d.cfg.get('node_info.enabled', True):
            churn_detector = NodeChurnDetector(d)
            fetcher_nodes.subscribe(churn_detector)

            notifier_nodes = NodeChurnNotifier(d)
            churn_detector.subscribe(notifier_nodes)

            tasks.append(fetcher_nodes)

            if d.cfg.get('node_info.version.enabled', True):
                notifier_version = VersionNotifier(d)
                churn_detector.subscribe(notifier_version)

            if d.cfg.get('node_op_tools.enabled', True):
                self.deps.node_op_notifier = NodeChangePersonalNotifier(d)
                await self.deps.node_op_notifier.prepare()
                churn_detector.subscribe(self.deps.node_op_notifier)

        if d.cfg.get('price.enabled', True):
            notifier_price = PriceNotifier(d)
            d.price_pool_fetcher.subscribe(notifier_price)

            if d.cfg.get('price.divergence.enabled', True):
                price_div_notifier = PriceDivergenceNotifier(d)
                d.price_pool_fetcher.subscribe(price_div_notifier)

        if d.cfg.get('pool_churn.enabled', True):
            period = parse_timespan_to_seconds(d.cfg.pool_churn.fetch_period)
            fetcher_pool_info = PoolInfoFetcherMidgard(d, period)
            notifier_pool_churn = PoolChurnNotifier(d)
            fetcher_pool_info.subscribe(notifier_pool_churn)
            tasks.append(fetcher_pool_info)

        if d.cfg.get('best_pools.enabled', True):
            period = parse_timespan_to_seconds(d.cfg.best_pools.fetch_period)
            fetcher_pool_info = PoolInfoFetcherMidgard(d, period)
            d.best_pools_notifier = BestPoolsNotifier(d)
            fetcher_pool_info.subscribe(d.best_pools_notifier)
            tasks.append(fetcher_pool_info)

        if d.cfg.get('chain_state.enabled', True):
            fetcher_chain_state = ChainStateFetcher(d)
            notifier_trade_halt = TradingHaltedNotifier(d)
            fetcher_chain_state.subscribe(notifier_trade_halt)
            tasks.append(fetcher_chain_state)

        if d.cfg.get('constants.mimir_change', True):
            notifier_mimir_change = MimirChangedNotifier(d)
            fetcher_mimir.subscribe(notifier_mimir_change)

        if d.cfg.get('constants.voting.enabled', True):
            voting_notifier = VotingNotifier(d)
            fetcher_mimir.subscribe(voting_notifier)

        if d.cfg.get('discord.enabled', False):
            d.discord_bot = DiscordBot(d.cfg)
            d.discord_bot.start_in_background()

        if d.cfg.get('slack.enabled', False):
            d.slack_bot = SlackBot(d.cfg, d.db)
            d.slack_bot.start_in_background()

        if d.cfg.get('bep2.enabled', True):
            fetcher_bep2 = BinanceOrgDexWSSClient()
            d.bep2_move_notifier = BEP2MoveNotifier(d)
            fetcher_bep2.subscribe(d.bep2_move_notifier)
            tasks.append(fetcher_bep2)

        self.deps.is_loading = False
        await asyncio.gather(*(task.run() for task in tasks))

    async def on_startup(self, _):
        self.deps.is_loading = True
        await self.connect_chat_storage()

        session_timeout = float(self.deps.cfg.get('thor.timeout', 2.0))
        self.deps.session = aiohttp.ClientSession(json_serialize=ujson.dumps,
                                                  timeout=ClientTimeout(total=session_timeout))

        logging.info(f'HTTP Session timeout is {session_timeout} sec')

        await self.create_thor_node_connector()

        asyncio.create_task(self._run_background_jobs())

    async def on_shutdown(self, _):
        await self.deps.session.close()

    def run_bot(self):
        self.create_bot_stuff()
        executor.start_polling(self.deps.dp, skip_updates=True,
                               on_startup=self.on_startup,
                               on_shutdown=self.on_shutdown)


if __name__ == '__main__':
    App().run_bot()
