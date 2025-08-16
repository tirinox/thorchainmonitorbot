import asyncio
import json

from tools.lib.lp_common import LpAppFramework

DEMO_POOL_LOGO_FILENAME = "./renderer/demo/dbg_pool_logo.json"


async def main():
    app = LpAppFramework()
    async with app:
        ph = await app.deps.pool_cache.get()
        pools = list(ph.pool_names)
        print(pools)

        with open(DEMO_POOL_LOGO_FILENAME, "w") as f:
            json.dump({
                "template_name": "dbg_pool_logo.jinja2",
                "parameters": {
                    "_width": 1280,
                    "_height": 920,
                    "pools": pools,
                }
            }, f, indent=2)


if __name__ == '__main__':
    asyncio.run(main())
