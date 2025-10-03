import asyncio
import json
import logging

from jobs.fetch.tcy import TCYInfoFetcher
from lib.texts import sep
from tools.lib.lp_common import LpAppFramework

DEMO_DATA_FILENAME_TCY = "./renderer/demo/tcy_info.json"


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


async def main():
    app = LpAppFramework(log_level=logging.DEBUG)
    async with app(brief=True):
        await dbg_tcy_data_collect(app)


if __name__ == '__main__':
    asyncio.run(main())
