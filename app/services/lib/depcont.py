import typing
from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiohttp import ClientSession

# from localization import LocalizationManager
# from services.fetch.node_ip_manager import ThorNodeAddressManager
# from services.lib.config import Config
# from services.lib.db import DB
from services.models.price import LastPriceHolder
from services.models.queue import QueueInfo
# from services.notify.broadcast import Broadcaster


# noinspection PyUnresolvedReferences
@dataclass
class DepContainer:
    cfg: typing.Optional['Config'] = None
    db: typing.Optional['DB'] = None

    session: typing.Optional[ClientSession] = None

    bot: typing.Optional['Bot'] = None
    dp: typing.Optional['Dispatcher'] = None

    thor_man: typing.Optional['ThorNodeAddressManager'] = None
    loc_man: typing.Optional['LocalizationManager'] = None
    broadcaster: typing.Optional['Broadcaster'] = None
    price_holder: LastPriceHolder = LastPriceHolder()
    queue_holder: QueueInfo = QueueInfo.error()
