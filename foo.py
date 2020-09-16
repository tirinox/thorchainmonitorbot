import asyncio
import aiohttp
import json


URL = lambda off, n: f"https://chaosnet-midgard.bepswap.com/v1/txs?offset={off}&limit={n}"
PLACE = lambda key: f'./datavar/transactions/{key}.json'
BATCH = 50



async def main():
    async with aiohttp.ClientSession() as session:
        count = await get_piece(0, BATCH, session)
        print(f'total count = {count}')
        for i in range(BATCH, count + 1, BATCH):
            await get_piece(i, BATCH, session)


async def get_piece(i, n, session):
    url = URL(i, n)
    print(f'getting {url}...')
    async with session.get(url) as resp:
        j = await resp.json()
        with open(PLACE(f"{i}_{n}"), "w") as f:
            json.dump(j, f, indent=4)
        return int(j['count'])


if __name__ == '__main__':
    asyncio.run(main())