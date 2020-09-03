import asyncio

import aiohttp

from config import Config


SLEEP_PERIOD = 60
MULT = 10 ** -8


async def fetch_caps(cfg: Config):
    urls = cfg.thorchain.chaosnet.urls

    async with aiohttp.ClientSession() as session:
        async with session.get(urls.network) as resp:
            networks_resp = await resp.json()
            total_staked = int(networks_resp.get('totalStaked', 0))

        async with session.get(urls.mimir) as resp:
            mimir_resp = await resp.json()
            max_staked = int(mimir_resp.get("mimir//MAXIMUMSTAKERUNE", 1))

        return {
            "total_staked": total_staked * MULT,
            "max_staked": max_staked * MULT
        }


async def fetch_loop(cfg: Config):
    await asyncio.sleep(5)

    old_max_cap = 0

    while True:
        r = await fetch_caps(cfg)

        max_cap = r['max_staked']
        if max_cap > old_max_cap:
            ...

        await asyncio.sleep(SLEEP_PERIOD)
