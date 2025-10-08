import asyncio
import json
import logging

from jobs.fetch.tcy import TCYInfoFetcher
from lib.constants import TCY_SYMBOL
from lib.texts import sep
from tools.lib.lp_common import LpAppFramework

DEMO_DATA_FILENAME_TCY = "./renderer/demo/tcy_info.json"


async def dbg_tcy_earnings(app):
    f = TCYInfoFetcher(app.deps)
    earnings = await f.get_earnings()
    sep()
    print(json.dumps(earnings, indent=4))


async def dbg_tcy_pool_depth_history(app):
    history = await app.deps.midgard_connector.query_pool_depth_history(TCY_SYMBOL, count=30, interval='day')
    print(history)


async def dbg_tcy_data_collect(app):
    f = TCYInfoFetcher(app.deps)
    data = await f.fetch()

    sep()

    raw = data.model_dump()

    with open(DEMO_DATA_FILENAME_TCY, "r") as f:
        existing_data = json.load(f)

    existing_data["parameters"].update(raw)
    with open(DEMO_DATA_FILENAME_TCY, "w") as f:
        json.dump(existing_data, f, indent=2)

    print(existing_data)


async def dbg_tcy_post_alert(app):
    ...


async def main():
    app = LpAppFramework(log_level=logging.DEBUG)
    async with app(brief=True):
        await dbg_tcy_data_collect(app)
        # await dbg_tcy_earnings(app)
        # await dbg_tcy_pool_depth_history(app)
        # await dbg_tcy_post_alert(app)


if __name__ == '__main__':
    asyncio.run(main())
