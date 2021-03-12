import asyncio
import logging
import os

import aiohttp
from aiothornode.connector import ThorConnector, TEST_NET_ENVIRONMENT_MULTI_1

from localization import LocalizationManager, EnglishLocalization
from services.dialog.price_picture import price_graph_from_db
from services.fetch.gecko_price import fill_rune_price_from_gecko
from services.lib.config import Config
from services.lib.db import DB
from services.lib.depcont import DepContainer


async def test_price_graph(d: DepContainer, renew=True):
    async with aiohttp.ClientSession() as d.session:
        await d.db.get_redis()
        d.thor_connector.session = d.session

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
    d.thor_connector = ThorConnector(TEST_NET_ENVIRONMENT_MULTI_1.copy(), d.session)
    d.db = DB(d.loop)
    d.loop.run_until_complete(test_price_graph(d, renew=True))
