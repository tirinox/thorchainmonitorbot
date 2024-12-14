import asyncio
import logging

from jobs.scanner.block_loader import thor_decode_amount_field
from jobs.scanner.native_scan_v3 import BlockScannerV3
from tools.lib.lp_common import LpAppFramework


async def dbg_get_block(app, block):
    d = app.deps
    scanner = BlockScannerV3(d, sleep_period=10.0)

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
        await dbg_get_block(app, block=18994647)


if __name__ == '__main__':
    asyncio.run(main())
