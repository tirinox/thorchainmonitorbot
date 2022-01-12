import asyncio
import logging

from services.lib.config import Config
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.lib.utils import setup_logs


class AppSettingsAPI:
    def __init__(self):
        d = self.deps = DepContainer()
        d.cfg = Config()

        log_level = d.cfg.get_pure('log_level', logging.INFO)
        setup_logs(log_level)

        logging.info(f'Starting Web API for THORChain monitoring bot @ "{d.cfg.network_id}".')

        d.price_holder.load_stable_coins(d.cfg)

        d.loop = asyncio.get_event_loop()
        d.db = DB(d.loop)

    def run(self):
        ...


if __name__ == '__main__':
    AppSettingsAPI().run()
