import asyncio
import logging

from jobs.scanner.native_scan import BlockScanner
from jobs.scanner.util import thor_decode_amount_field, pubkey_to_thor_address
from tools.lib.lp_common import LpAppFramework

"""
Contains error tx: 18995227
Contains send tx: 18994586
"""


async def dbg_get_block(app, block):
    d = app.deps
    scanner = BlockScanner(d, sleep_period=10.0)

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
    # print(pubkey_to_thor_address("A7dfWmk8lROhAOMYrSx/XaVc1U27nT73WSLpbUzany5I"))
    # dbg_decode_thor_amounts()

    app = LpAppFramework(log_level=logging.DEBUG)
    async with app(brief=True):
        # await dbg_get_block(app, block=19999647)
        await dbg_get_block(app, block=1999647)


if __name__ == '__main__':
    asyncio.run(main())
