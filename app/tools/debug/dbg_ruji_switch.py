import asyncio

from jobs.fetch.ruji_merge import RujiMergeStatsFetcher
from jobs.scanner.native_scan import BlockScanner
from jobs.scanner.ruji_switch import RujiSwitchEventDecoder
from tools.lib.lp_common import LpAppFramework, Receiver


async def dbg_switch_event_continuous(app: LpAppFramework, force_start_block=None, catch_up=0, one_block=False):
    d = app.deps
    d.block_scanner = BlockScanner(d)
    d.block_scanner.initial_sleep = 0

    await d.pool_fetcher.run_once()
    d.last_block_fetcher.add_subscriber(d.last_block_store)
    await d.last_block_fetcher.run_once()

    # AffiliateRecorder
    # d.affiliate_recorder = AffiliateRecorder(d)
    # d.block_scanner.add_subscriber(d.affiliate_recorder)
    ruji_switch_decoder = RujiSwitchEventDecoder(d.db, d.price_holder)
    d.block_scanner.add_subscriber(ruji_switch_decoder)

    ruji_switch_decoder.add_subscriber(Receiver("switch"))

    if catch_up > 0:
        await d.block_scanner.ensure_last_block()
        d.block_scanner.last_block -= catch_up
    elif force_start_block:
        d.block_scanner.last_block = force_start_block

    if one_block:
        d.block_scanner.one_block_per_run = True
        await d.block_scanner.run_once()
    else:
        await d.block_scanner.run()


async def dbg_mering_coin_gecko_prices(app):
    f = RujiMergeStatsFetcher(app.deps)
    prices = await f.get_prices_usd_from_gecko()
    print(prices)


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        # await dbg_switch_event_continuous(app, force_start_block=20639864)
        await dbg_mering_coin_gecko_prices(app)


if __name__ == '__main__':
    asyncio.run(run())
