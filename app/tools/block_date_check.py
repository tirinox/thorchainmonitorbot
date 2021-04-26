import asyncio
import datetime

import aiohttp

NODE_IP = '164.90.245.92'
NODE_RPC_PORT = 27147


def url_gen_block(block_height):
    return f'http://{NODE_IP}:{NODE_RPC_PORT}/block?height={block_height}'


async def get_block_info(session, height):
    url = url_gen_block(height)
    print(f'get: {url}')
    async with session.get(url) as resp:
        resp = await resp.json()
        return resp


def date_parse(s: str):
    s = s.rstrip('Z')
    s = s[:-3]
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f")


async def main():
    async with aiohttp.ClientSession() as session:
        r = await get_block_info(session, 1000)
        iso_time = r['result']['block']['header']['time']
        time = date_parse(iso_time)
        print(time.timestamp())


if __name__ == '__main__':
    asyncio.run(main())
