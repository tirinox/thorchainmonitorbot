import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Set, Dict

import aiohttp
import ujson
from aiogram import Bot, Dispatcher
from aiohttp import ClientSession, ClientTimeout
from aiothornode.connector import ThorConnector
from aiothornode.types import ThorChainInfo

from services.lib.config import Config
from services.lib.db import DB
from services.lib.midgard.connector import MidgardConnector
from services.models.mimir import MimirHolder
from services.models.node_info import NodeListHolder
from services.models.price import LastPriceHolder
from services.models.queue import QueueInfo


@dataclass
class DepContainer:
    cfg: Optional[Config] = None
    db: Optional[DB] = None
    loop: Optional[asyncio.BaseEventLoop] = None

    session: Optional[ClientSession] = None

    bot: Optional[Bot] = None
    dp: Optional[Dispatcher] = None

    thor_connector: Optional[ThorConnector] = None
    midgard_connector: Optional[MidgardConnector] = None

    rune_market_fetcher = None  # type: 'RuneMarketInfoFetcher'

    loc_man = None  # type: 'LocalizationManager'
    broadcaster = None  # type: 'Broadcaster'

    price_pool_fetcher = None  # type: 'PoolPriceFetcher'
    node_info_fetcher = None  # type: 'NodeInfoFetcher'
    mimir_const_fetcher = None  # type: 'ConstMimirFetcher'

    node_op_notifier = None  # type: 'NodeChangePersonalNotifier'
    block_notifier = None  # type: 'BlockHeightNotifier'
    best_pools_notifier = None  # type: 'BestPoolsNotifier'
    bep2_move_notifier = None  # type: 'BEP2MoveNotifier'

    discord_bot = None
    slack_bot = None

    # shared data holders

    price_holder: LastPriceHolder = LastPriceHolder()
    queue_holder: QueueInfo = QueueInfo.error()
    mimir_const_holder: Optional[MimirHolder] = None
    halted_chains: Set[str] = field(default_factory=set)
    chain_info: Dict[str, ThorChainInfo] = field(default_factory=dict)
    node_holder: NodeListHolder = NodeListHolder()

    is_loading = True

    def make_http_session(self):
        session_timeout = float(self.cfg.get('thor.timeout', 2.0))
        self.session = aiohttp.ClientSession(
            json_serialize=ujson.dumps,
            timeout=ClientTimeout(total=session_timeout))
        logging.info(f'HTTP Session timeout is {session_timeout} sec')


