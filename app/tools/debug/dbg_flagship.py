import asyncio
import logging

from lib.flagship import Flagship
from lib.texts import sep
from tools.lib.lp_common import LpAppFramework


def print_hierarchy(data, indent=0):
    for key, value in data.items():
        print(' ' * indent + str(key) + ':', end=' ')
        if isinstance(value, dict):
            print()
            print_hierarchy(value, indent + 2)
        else:
            print(str(value))


async def dbg_flagship(app):
    f = Flagship(app.deps.db)

    foo = await f.is_flag_set("debug:foo")
    print(f"debug:foo = {foo}")
    sep()

    bar = await f.is_flag_set("debug:bar")
    print(f"debug:bar = {bar}")
    sep()

    await f.set_flag("debug:set:false", False)

    data = await f.get_all_hierarchy()
    print_hierarchy(data)


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        await dbg_flagship(app)


if __name__ == '__main__':
    asyncio.run(main())
