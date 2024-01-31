import asyncio
import logging

import tqdm
from redis.asyncio import Redis

from services.lib.constants import THOR_BLOCK_TIME
from services.lib.date_utils import DAY
from services.lib.money import format_percent
from tools.lib.lp_common import LpAppFramework

MAX_AGE = 30 * DAY


async def do_job(app):
    r: Redis = await app.deps.db.get_redis()
    logging.info('Loading all txs from DB')
    tx_keys = await r.keys('tx:tracker:*')
    logging.info(f'Found {len(tx_keys)} txs')
    if not tx_keys:
        logging.error('No txs found!')
        return

    top_blocks = await app.deps.thor_connector.query_last_blocks()
    assert top_blocks
    top_block = top_blocks[0].thorchain
    logging.info(f'Top block is {top_block}')
    assert top_block > 0

    min_block = int(max(1, top_block - MAX_AGE / THOR_BLOCK_TIME))
    logging.warning(f'I will remove all records prior to block #{min_block}')
    if input('Are you sure? (y/n): ').lower().strip() != 'y':
        return

    none_height_blocks = 0
    old_blocks = 0

    for tx_key in tqdm.tqdm(tx_keys):
        block_height = await r.hget(tx_key, 'block_height')
        if block_height is None:
            block_height = 0
            none_height_blocks += 1
        elif block_height:
            block_height = int(block_height)

        block_height = int(block_height)
        will_delete = block_height < min_block
        if will_delete:
            old_blocks += 1
            await r.delete(tx_key)
        # print(f"Block height: {block_height}; will delete? {block_height < min_block}")

    print(f'None height blocks: {none_height_blocks} ({format_percent(none_height_blocks, len(tx_keys))})')
    print(f"Old blocks: {old_blocks} ({format_percent(old_blocks, len(tx_keys))})")


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app(brief=True):
        await do_job(app)


if __name__ == "__main__":
    asyncio.run(main())
