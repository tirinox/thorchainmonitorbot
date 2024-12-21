import logging

import aiofiles
import aiohttp


async def download_file(url, target_path):
    async with aiohttp.ClientSession() as session:
        if not url:
            raise FileNotFoundError

        logging.info(f'Downloading file from {url}...')
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(target_path, mode='wb')
                await f.write(await resp.read())
                await f.close()

            return resp.status
