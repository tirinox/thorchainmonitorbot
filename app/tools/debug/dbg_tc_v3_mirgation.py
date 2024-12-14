import asyncio
import logging

from jobs.scanner.native_scan import BlockScanner
from proto.access import thor_decode_amount_field
from tools.lib.lp_common import LpAppFramework


async def dbg_get_block(app, block):
    d = app.deps
    scanner = BlockScanner(d, sleep_period=10.0)

    d.last_block_fetcher.add_subscriber(d.last_block_store)
    await d.last_block_fetcher.run_once()

    block = await scanner.fetch_one_block(block)
    print(block)


def dbg_decode_thor_amounts():
    amt, asset = thor_decode_amount_field("35168311000 THOR.RUNE")
    assert amt == 35168311000
    assert asset == "THOR.RUNE"
    print(amt, asset)

    amt, asset = thor_decode_amount_field("15848 ETH/ETH")
    assert amt == 15848
    assert asset == "ETH/ETH"
    print(amt, asset)

    # 48287975rune"
    amt, asset = thor_decode_amount_field("48287975rune")
    assert amt == 48287975
    assert asset == "RUNE"
    print(amt, asset)


async def main():
    dbg_decode_thor_amounts()

    app = LpAppFramework(log_level=logging.DEBUG)
    async with app(brief=True):
        await dbg_get_block(app, block=18976830)


if __name__ == '__main__':
    asyncio.run(main())
