import asyncio
from dataclasses import dataclass, field
from typing import Optional, Set, Dict

from aiogram import Bot, Dispatcher
from aiohttp import ClientSession
from aiothornode.connector import ThorConnector
from aiothornode.types import ThorChainInfo

from services.lib.config import Config
from services.lib.db import DB
from services.lib.midgard.connector import MidgardConnector
from services.models.mimir import MimirHolder
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

    loc_man: Optional['LocalizationManager'] = None
    broadcaster: Optional['Broadcaster'] = None

    price_pool_fetcher: Optional['PoolPriceFetcher'] = None
    node_info_fetcher: Optional['NodeInfoFetcher'] = None
    mimir_const_fetcher: Optional['ConstMimirFetcher'] = None

    node_op_notifier: Optional['NodeChangePersonalNotifier'] = None

    # shared data holders

    price_holder: LastPriceHolder = LastPriceHolder()
    queue_holder: QueueInfo = QueueInfo.error()
    mimir_const_holder: Optional[MimirHolder] = None
    halted_chains: Set[str] = field(default_factory=set)
    chain_info: Dict[str, ThorChainInfo] = field(default_factory=dict)
