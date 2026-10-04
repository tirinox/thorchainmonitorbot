import asyncio
import logging

from comm.picture.crypto_logo import CryptoLogoDownloader, check_pool_logos
from comm.picture.resources import Resources
from models.price import PriceHolder
from tools.lib.lp_common import LpAppFramework


async def do_download_job(app):
    """Downloads the missing logos of all the pools, of their chains and of RUNE, and tells what cannot be got"""
    ph: PriceHolder = await app.deps.pool_cache.get()
    pools = sorted(ph.pool_names | {'THOR.RUNE'})
    print(pools)

    problems = await check_pool_logos(CryptoLogoDownloader(Resources().LOGO_BASE), pools)
    print(f'{len(pools)} pools checked, {len(problems)} problems')
    for logo, problem in problems.items():
        print(f'NO LOGO {logo}: {problem}')


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        await do_download_job(app)


if __name__ == "__main__":
    asyncio.run(main())
