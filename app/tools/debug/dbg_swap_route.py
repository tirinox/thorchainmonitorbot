import asyncio

from jobs.scanner.native_scan import BlockScanner
from jobs.scanner.swap_extractor import SwapExtractorBlock
from jobs.scanner.swap_routes import SwapRouteRecorder
from jobs.volume_filler import VolumeFillerUpdater
from jobs.volume_recorder import VolumeRecorder, TxCountRecorder
from lib.texts import sep
from tools.lib.lp_common import LpAppFramework


async def dbg_print_top_swap_routes(app: LpAppFramework):
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


async def tool_record_swap_routes(app: LpAppFramework, start_block: int = -1):
    d = app.deps

    if start_block is not None and start_block < 0:
        thor = await app.deps.last_block_cache.get_thor_block()
        assert thor > 0
        start_block = thor + start_block
    else:
        start_block = 0

    d.block_scanner = BlockScanner(d, max_attempts=3, last_block=start_block)
    native_action_extractor = SwapExtractorBlock(d)
    d.block_scanner.add_subscriber(native_action_extractor)

    volume_filler = VolumeFillerUpdater(d)
    native_action_extractor.add_subscriber(volume_filler)

    d.volume_recorder = VolumeRecorder(d)
    volume_filler.add_subscriber(d.volume_recorder)

    d.tx_count_recorder = TxCountRecorder(d)
    volume_filler.add_subscriber(d.tx_count_recorder)

    # Swap route recorder
    d.route_recorder = SwapRouteRecorder(d.db)
    volume_filler.add_subscriber(d.route_recorder)

    await d.block_scanner.run()


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        await tool_record_swap_routes(app, -10 * 60 * 24 * 14)


if __name__ == '__main__':
    asyncio.run(main())
