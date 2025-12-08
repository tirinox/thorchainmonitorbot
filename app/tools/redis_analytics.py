# Instruction:
# $ make attach
# $ PYTHONPATH="/app" python tools/redis_analytics.py /config/config.yaml
import asyncio
import logging

import tqdm
from redis.asyncio import Redis

from tools.lib.lp_common import LpAppFramework


async def do_job(app):
    r: Redis = await app.deps.db.get_redis()
    logging.info('Loading all txs from DB')
    tx_keys = await r.keys()
    logging.info(f'Found {len(tx_keys)} txs')

    results = []
    types = set()
    for key in tqdm.tqdm(tx_keys):
        key_type = await r.type(key)

        if key_type == 'none':
            # try again
            await asyncio.sleep(0.1)
            key_type = await r.type(key)
        
        if key_type == 'hash':
            data_len = await r.hlen(key)
        elif key_type == 'set':
            data_len = await r.scard(key)
        elif key_type == 'zset':
            data_len = await r.zcard(key)
        elif key_type == 'stream':
            data_len = await r.xlen(key)
        elif key_type == 'string':
            data_len = 1
        else:
            logging.warning(f'Unknown type {key_type} for key {key}')
            data_len = 1
        results.append((key, key_type, data_len))
        types.add(key_type)

    logging.info(f'Types: {types}')

    results.sort(key=lambda x: x[2], reverse=True)
    for i, (key, key_type, data_len) in enumerate(results[:100], start=1):
        print(f'{i: 4}. ({data_len: 6} items): {key} (dt={key_type})')


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        await do_job(app)


if __name__ == "__main__":
    asyncio.run(main())
