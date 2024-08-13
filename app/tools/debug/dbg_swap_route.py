import asyncio

from services.jobs.scanner.swap_routes import SwapRouteRecorder
from services.lib.texts import sep
from tools.lib.lp_common import LpAppFramework


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        route_recorded = SwapRouteRecorder(app.deps.db)
        routes = await route_recorded.get_top_swap_routes_by_volume(top_n=12)

        sep('NORMAL')

        for route in routes:
            print(route)

        sep('NORMALIZED')
        routes = await route_recorded.get_top_swap_routes_by_volume(top_n=12, normalize_assets=True)

        for route in routes:
            print(route)

        sep('REORDERED and NORMALIZED')
        routes = await route_recorded.get_top_swap_routes_by_volume(top_n=12, reorder_assets=True, normalize_assets=True)

        for route in routes:
            print(route)

if __name__ == '__main__':
    asyncio.run(main())
