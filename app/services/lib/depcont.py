import typing
import asyncio
from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiohttp import ClientSession

from services.models.price import LastPriceHolder
from services.models.queue import QueueInfo

from aiothornode.connector import ThorConnector


@dataclass
class DepContainer:
    cfg: typing.Optional['Config'] = None
    db: typing.Optional['DB'] = None
    loop: typing.Optional[asyncio.BaseEventLoop] = None

    session: typing.Optional[ClientSession] = None

    bot: typing.Optional['Bot'] = None
    dp: typing.Optional['Dispatcher'] = None

    thor_connector: typing.Optional[ThorConnector] = None

    loc_man: typing.Optional['LocalizationManager'] = None
    broadcaster: typing.Optional['Broadcaster'] = None
    price_holder: LastPriceHolder = LastPriceHolder()
    queue_holder: QueueInfo = QueueInfo.error()
