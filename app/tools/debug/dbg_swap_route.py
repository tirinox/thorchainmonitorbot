import asyncio

from services.jobs.scanner.swap_routes import SwapRouteRecorder
from tools.lib.lp_common import LpAppFramework


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        route_recorded = SwapRouteRecorder(app.deps.db)
        routes = await route_recorded.get_top_swap_routes_by_volume(top_n=10)

        for route in routes:
            print(route)
            print('---')


if __name__ == '__main__':
    asyncio.run(main())