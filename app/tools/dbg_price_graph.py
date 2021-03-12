import asyncio
import logging
import os

import aiohttp

from localization import LocalizationManager, RussianLocalization, EnglishLocalization
from services.dialog.price_picture import price_graph, price_graph_from_db
from services.fetch.gecko_price import fill_rune_price_from_gecko
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.lib.config import Config
from services.lib.datetime import DAY, series_to_pandas
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.models.time_series import PriceTimeSeries
from services.lib.constants import RUNE_SYMBOL, RUNE_SYMBOL_DET


async def test_price_graph(d: DepContainer, renew=True):
    async with aiohttp.ClientSession() as d.session:
        await d.db.get_redis()
        d.thor_man.session = d.session

        if renew:
            await fill_rune_price_from_gecko(d.db, include_fake_det=True)

        img = await price_graph_from_db(d.db, EnglishLocalization())

        picture_path = '../../price.png'
        img.save(picture_path, "PNG")
        os.system(f'open "{picture_path}"')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.cfg = Config()
    d.loc_man = LocalizationManager()
    d.thor_man = ThorNodeAddressManager(d.cfg.thornode.seed)
    d.db = DB(d.loop)
    d.loop.run_until_complete(test_price_graph(d, renew=True))
