import asyncio
import logging

import tqdm

from comm.picture.crypto_logo import CryptoLogoDownloader
from comm.picture.resources import Resources
from models.price import PriceHolder
from tools.lib.lp_common import LpAppFramework


async def do_download_job(app):
    ph: PriceHolder = await app.deps.pool_cache.get()
    pools = ph.pool_names
    print(pools)

    pools.add('THOR.RUNE')

    logo_downloader = CryptoLogoDownloader(Resources().LOGO_BASE)
    for pool in tqdm.tqdm(pools):
        await logo_downloader.get_or_download_logo_cached(pool)


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app(brief=True):
        await do_download_job(app)


if __name__ == "__main__":
    asyncio.run(main())
