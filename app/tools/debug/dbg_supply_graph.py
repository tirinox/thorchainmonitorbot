import asyncio
import dataclasses
import os
from io import BytesIO

from localization.languages import Language
from localization.manager import LocalizationManager
from services.dialog.picture.supply_picture import SupplyPictureGenerator
from services.jobs.fetch.killed_rune import KilledRuneFetcher
from services.lib.utils import json_cached_to_file_async
from services.models.killed_rune import KilledRuneEntry
from services.models.price import RuneMarketInfo
from tools.lib.lp_common import LpAppFramework


@json_cached_to_file_async("../temp/killed_rune.json")
async def get_killed_rune(app: LpAppFramework):
    krf = KilledRuneFetcher(app.deps)
    data = await krf.fetch()
    return data[0].__dict__


@json_cached_to_file_async("../temp/supply_info.json")
async def get_rune_supply(app: LpAppFramework):
    rune_market_info: RuneMarketInfo = await app.deps.rune_market_fetcher.get_rune_market_info()
    return dataclasses.asdict(rune_market_info.supply_info)


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        loc_man: LocalizationManager = app.deps.loc_man
        loc = loc_man.get_from_lang(Language.RUSSIAN)

        data = await get_killed_rune(app)
        killed_rune = KilledRuneEntry(**data)

        rune_market_info: RuneMarketInfo = await app.deps.rune_market_fetcher.get_rune_market_info()

        pic_gen = SupplyPictureGenerator(loc, rune_market_info.supply_info, killed_rune)
        pic: BytesIO
        pic = await pic_gen.get_picture()

        filepath = '../temp/supply.png'
        with open(filepath, 'wb') as f:
            # noinspection PyTypeChecker
            f.write(pic.getbuffer())

        os.system(f'open "{filepath}"')


if __name__ == '__main__':
    asyncio.run(run())
