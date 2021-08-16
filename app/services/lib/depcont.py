import asyncio
from dataclasses import dataclass, field
from typing import Optional, Set

from aiogram import Bot, Dispatcher
from aiohttp import ClientSession
from aiothornode.connector import ThorConnector

from services.lib.config import Config
from services.lib.db import DB
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

    loc_man: Optional['LocalizationManager'] = None
    broadcaster: Optional['Broadcaster'] = None

    price_pool_fetcher: Optional['PoolPriceFetcher'] = None
    node_info_fetcher: Optional['NodeInfoFetcher'] = None

    # shared data holders

    price_holder: LastPriceHolder = LastPriceHolder()
    queue_holder: QueueInfo = QueueInfo.error()
    mimir_const_holder: Optional['ConstMimirFetcher'] = None
    halted_chains: Set[str] = field(default_factory=set)
