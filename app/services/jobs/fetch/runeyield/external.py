from typing import List

from aiohttp import ClientSession


async def get_user_pools_from_thoryield(session: ClientSession, address: str) -> List[str]:
    url = f'https://multichain-asgard-consumer-api.vercel.app/api/v3/member/poollist?address={address}'
    async with session.get(url) as resp:
        if resp.status != 200:
            return []
        j = await resp.json()

        results = []
        for item in j:
            results.append(item['pool'])
        return results
