import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Set, Dict

import ujson
from aiohttp import ClientSession, ClientTimeout
from aiothornode.connector import ThorConnector
from aiothornode.env import ThorEnvironment
from aiothornode.types import ThorChainInfo

from services.dialog.telegram.telegram import TelegramBot
from services.dialog.twitter.twitter_bot import TwitterBot
from services.lib.config import Config
from services.lib.db import DB
from services.lib.emergency import EmergencyReport
from services.lib.http_ses import ObservableSession
from services.lib.midgard.connector import MidgardConnector
from services.lib.midgard.name_service import NameService
from services.lib.new_feature import NewFeatureManager, Features
from services.lib.scheduler import Scheduler
from services.lib.settings_manager import SettingsManager
from services.models.mimir import MimirHolder
from services.models.net_stats import NetworkStats
from services.models.node_info import NodeListHolder
from services.models.node_watchers import AlertWatchers
from services.models.price import LastPriceHolder
from services.models.queue import QueueInfo
from services.notify.channel import Messengers


@dataclass
class DepContainer:
    cfg: Optional[Config] = None
    db: Optional[DB] = None
    loop: Optional[asyncio.BaseEventLoop] = None
    loc_man = None  # type: 'LocalizationManager'
    broadcaster = None  # type: 'Broadcaster'
    alert_presenter = None
    thor_env: ThorEnvironment = ThorEnvironment()

    session: Optional[ClientSession] = None

    thor_connector: Optional[ThorConnector] = None
    midgard_connector: Optional[MidgardConnector] = None

    name_service: Optional[NameService] = None

    block_scanner = None

    rune_market_fetcher = None  # type: 'RuneMarketInfoFetcher'

    pool_fetcher = None  # type: 'PoolFetcher'
    node_info_fetcher = None  # type: 'NodeInfoFetcher'
    mimir_const_fetcher = None  # type: 'ConstMimirFetcher'
    last_block_fetcher = None  # type: 'LastBlockFetcher'
    saver_stats_fetcher = None
    data_controller = None

    node_op_notifier = None  # type: 'NodeChangePersonalNotifier'
    block_notifier = None  # type: 'BlockHeightNotifier'
    best_pools_notifier = None  # type: 'BestPoolsNotifier'
    rune_move_notifier = None  # type: 'RuneMoveNotifier'
    volume_recorder = None  # type: 'VolumeRecorder'
    weekly_stats_notifier = None
    pol_notifier = None

    dex_analytics = None

    scheduler: Optional[Scheduler] = None

    gen_alert_settings_proc = None
    alert_watcher: Optional[AlertWatchers] = None

    telegram_bot: Optional[TelegramBot] = None
    discord_bot = None
    slack_bot = None
    twitter_bot: Optional[TwitterBot] = None

    # shared data holders

    price_holder: LastPriceHolder = LastPriceHolder()
    queue_holder: QueueInfo = QueueInfo.error()
    mimir_const_holder: Optional[MimirHolder] = None
    halted_chains: Set[str] = field(default_factory=set)
    chain_info: Dict[str, ThorChainInfo] = field(default_factory=dict)
    node_holder: NodeListHolder = NodeListHolder()
    net_stats: NetworkStats = NetworkStats()
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
