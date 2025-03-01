import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, List

import ujson
from aiohttp import ClientSession, ClientTimeout

from api.aionode.connector import ThorConnector
from api.aionode.types import ThorChainInfo
from api.midgard.connector import MidgardConnector
from api.midgard.name_service import NameService
from comm.telegram.telegram import TelegramBot
from comm.twitter.twitter_bot import TwitterBot
from lib.config import Config
from lib.db import DB
from lib.emergency import EmergencyReport
from lib.http_ses import ObservableSession
from lib.new_feature import NewFeatureManager, Features
from lib.scheduler import Scheduler
from lib.settings_manager import SettingsManager
from models.mimir import MimirHolder
from models.net_stats import NetworkStats
from models.node_info import NodeListHolder
from models.node_watchers import AlertWatchers
from models.price import LastPriceHolder
from models.queue import QueueInfo
from notify.channel import Messengers


@dataclass
class DepContainer:
    cfg: Optional[Config] = None
    db: Optional[DB] = None
    loop: Optional[asyncio.BaseEventLoop] = None
    loc_man = None  # type: 'LocalizationManager'
    broadcaster = None  # type: 'Broadcaster'
    alert_presenter = None

    session: Optional[ClientSession] = None

    thor_connector: Optional[ThorConnector] = None
    thor_connector_archive: Optional[ThorConnector] = None
    midgard_connector: Optional[MidgardConnector] = None

    name_service: Optional[NameService] = None

    block_scanner = None  # type: 'NativeScannerBlock'

    rune_market_fetcher = None  # type: 'RuneMarketInfoFetcher'

    pool_fetcher = None  # type: 'PoolFetcher'
    node_info_fetcher = None  # type: 'NodeInfoFetcher'
    mimir_const_fetcher = None  # type: 'ConstMimirFetcher'
    last_block_fetcher = None  # type: 'LastBlockFetcher'
    saver_stats_fetcher = None
    data_controller = None
    lend_stats_fetcher = None
    trade_acc_fetcher = None  # type: 'TradeAccountFetcher'

    node_op_notifier = None  # type: 'NodeChangePersonalNotifier'
    block_notifier = None  # type: 'BlockHeightNotifier'
    best_pools_notifier = None  # type: 'BestPoolsNotifier'
    rune_move_notifier = None  # type: 'RuneMoveNotifier'
    tr_acc_summary_notifier = None  # type: 'TradeAccSummaryNotifier'
    volume_recorder = None  # type: 'VolumeRecorder'
    tx_count_recorder = None  # type: 'TxCountRecorder'
    user_counter = None  # type: 'UserCounterMiddleware'
    weekly_stats_notifier = None
    pol_notifier = None
    lend_stats_notifier = None

    dex_analytics = None
    affiliate_recorder = None
    route_recorder = None

    scheduler: Optional[Scheduler] = None

    gen_alert_settings_proc = None
    alert_watcher: Optional[AlertWatchers] = None

    telegram_bot: Optional[TelegramBot] = None
    discord_bot = None
    slack_bot = None
    twitter_bot: Optional[TwitterBot] = None

    # shared data holders

    price_holder: LastPriceHolder = field(default_factory=LastPriceHolder)
    queue_holder: QueueInfo = field(default_factory=QueueInfo.error)
    mimir_const_holder: Optional[MimirHolder] = None
    halted_chains: List[str] = field(default_factory=list)
    chain_info: Dict[str, ThorChainInfo] = field(default_factory=dict)
    node_holder: NodeListHolder = field(default_factory=NodeListHolder)
    net_stats: NetworkStats = field(default_factory=NetworkStats)
    last_block_store = None

    emergency: Optional[EmergencyReport] = None

    settings_manager: Optional[SettingsManager] = None

    is_loading: bool = True

    new_feature: NewFeatureManager = NewFeatureManager(Features.EXPIRE_TABLE)

    def make_http_session(self):
        session_timeout = self.cfg.get_timeout_global
        self.session = ObservableSession(
            json_serialize=ujson.dumps,
            timeout=ClientTimeout(total=session_timeout))
        logging.info(f'HTTP Session timeout is {session_timeout} sec')

    def get_messenger(self, t: str):
        return {
            Messengers.TELEGRAM: self.telegram_bot,
            Messengers.TWITTER: self.twitter_bot,
            Messengers.SLACK: self.slack_bot,
            Messengers.DISCORD: self.discord_bot,
        }.get(t)
