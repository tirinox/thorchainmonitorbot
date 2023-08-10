import asyncio

from services.jobs.fetch.streaming_swaps import StreamingSwapFechter
from tools.lib.lp_common import LpAppFramework


SS_EXAMPLE = '75327336C1EC3FE39D1DECB06C5F05756FAA5C28E0ACC777239F98D7F2903589'
# Memo:  =:ETH.THOR:0x8d2e7cab1747f98a7e1fa767c9ef62132e4c31db:139524325459200/9/99:t:30
# Mdg: https://midgard.ninerealms.com/v2/actions?txid=75327336C1EC3FE39D1DECB06C5F05756FAA5C28E0ACC777239F98D7F2903589
# VB: https://viewblock.io/thorchain/tx/75327336C1EC3FE39D1DECB06C5F05756FAA5C28E0ACC777239F98D7F2903589
# Inb: https://thornode.ninerealms.com/thorchain/tx/75327336C1EC3FE39D1DECB06C5F05756FAA5C28E0ACC777239F98D7F2903589



async def debug_fetch_ss(app: LpAppFramework):
    ssf = StreamingSwapFechter(app.deps)
    data = await ssf.run_once()
    print(data)


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        await debug_fetch_ss(app)


if __name__ == '__main__':
    asyncio.run(run())
