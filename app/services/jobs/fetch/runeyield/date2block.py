import logging
from datetime import date, datetime, timedelta
from typing import Dict

from aioredis import Redis

from services.lib.constants import THOR_BLOCK_TIME
from services.lib.date_utils import day_to_key, days_ago_noon, DAY
from services.lib.depcont import DepContainer
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import get_url_gen_by_network_id
from services.models.last_block import LastBlock


class DateToBlockMapper:
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.midgard_url_gen = get_url_gen_by_network_id(deps.cfg.network_id)
        self.midgard_parser = get_parser_by_network_id(deps.cfg.network_id)
        self.logger = logging.getLogger(self.__class__.__name__)

    async def get_last_blocks(self) -> Dict[str, LastBlock]:
        url_last_block = self.midgard_url_gen.url_last_block()
        self.logger.info(f"get: {url_last_block}")

        async with self.deps.session.get(url_last_block) as resp:
            raw_data = await resp.json()
            last_blocks = self.midgard_parser.parse_last_block(raw_data)
            return last_blocks

    DB_KEY_DATE_TO_BLOCK_MAPPER = 'Date2Block:Thorchain'

    async def clear(self):
        r: Redis = await self.deps.db.get_redis()
        await r.delete(self.DB_KEY_DATE_TO_BLOCK_MAPPER)

    async def save_height_to_day_cache(self, day: date, block_height):
        r: Redis = await self.deps.db.get_redis()
        await r.hset(self.DB_KEY_DATE_TO_BLOCK_MAPPER, day_to_key(day), block_height)

    async def load_height_from_day_cache(self, day) -> int:
        r: Redis = await self.deps.db.get_redis()
        data = await r.hget(self.DB_KEY_DATE_TO_BLOCK_MAPPER, day_to_key(day))
        return int(data) if data else None

    async def calibrate(self, days=14):
        last_blocks = await self.get_last_blocks()
        last_block: LastBlock = list(last_blocks.values())[0]
        now = datetime.now()
        today_beginning = days_ago_noon(0, hour=0)

        blocks_from_day_beginning = (now.timestamp() - today_beginning.timestamp()) / THOR_BLOCK_TIME
        blocks_per_day = DAY / THOR_BLOCK_TIME

        blocks = []

        for day_ago in range(days):
            that_day = days_ago_noon(day_ago, hour=0)
            block_that_day = int(last_block.thorchain - blocks_from_day_beginning - blocks_per_day * day_ago)
            block_that_day = max(0, block_that_day)

            print(f'{day_ago = }, {that_day = }, {block_that_day = }')  # fixme: debug
            blocks.append((that_day, block_that_day))

        print(blocks)  # fixme: debug

    async def get_block_height_by_date(self, d: date) -> int:
        return 0  # todo
