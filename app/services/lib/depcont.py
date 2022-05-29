import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Set, Dict

import aiohttp
import ujson
from aiohttp import ClientSession, ClientTimeout
from aiothornode.connector import ThorConnector
from aiothornode.types import ThorChainInfo

from services.dialog.telegram.telegram import TelegramBot
from services.dialog.twitter.twitter_bot import TwitterBot
from services.lib.config import Config
from services.lib.db import DB
from services.lib.midgard.connector import MidgardConnector
from services.lib.new_feature import NewFeatureManager
from services.lib.settings_manager import SettingsManager
from services.models.mimir import MimirHolder
from services.models.node_info import NodeListHolder
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

    session: Optional[ClientSession] = None

    thor_connector: Optional[ThorConnector] = None
    midgard_connector: Optional[MidgardConnector] = None

    rune_market_fetcher = None  # type: 'RuneMarketInfoFetcher'

    price_pool_fetcher = None  # type: 'PoolPriceFetcher'
    node_info_fetcher = None  # type: 'NodeInfoFetcher'
    mimir_const_fetcher = None  # type: 'ConstMimirFetcher'

    node_op_notifier = None  # type: 'NodeChangePersonalNotifier'
    block_notifier = None  # type: 'BlockHeightNotifier'
    best_pools_notifier = None  # type: 'BestPoolsNotifier'
    bep2_move_notifier = None  # type: 'BEP2MoveNotifier'

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

    settings_manager: Optional[SettingsManager] = None

    is_loading: bool = True

    new_feature: NewFeatureManager = NewFeatureManager()

    def make_http_session(self):
        session_timeout = float(self.cfg.get('thor.timeout', 2.0))
        self.session = aiohttp.ClientSession(
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
