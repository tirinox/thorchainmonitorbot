from datetime import date, datetime, timedelta

from redis.asyncio import Redis

from api.aionode.types import ThorLastBlock
from api.midgard.parser import get_parser_by_network_id
from lib.constants import THOR_BLOCK_TIME
from lib.date_utils import day_to_key, days_ago_noon, date_parse_rfc
from lib.depcont import DepContainer
from lib.logs import WithLogger


class DateToBlockMapper(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.midgard_parser = get_parser_by_network_id(deps.cfg.network_id)

        self.iterative_algo_max_steps = 10
        self.iterative_algo_tolerance = THOR_BLOCK_TIME * 1.6

    async def get_last_thorchain_block(self) -> int:
        return await self.deps.last_block_cache.get_thor_block()

    async def get_timestamp_by_block_height(self, block_height) -> float:
        block_info = await self.deps.thor_connector.query_tendermint_block_raw(block_height)
        if not block_info or 'result' not in block_info:
            return -1

        rfc_time = block_info['result']['block']['header']['time']
        dt = date_parse_rfc(rfc_time)
        return dt.timestamp()

    DB_KEY_DATE_TO_BLOCK_MAPPER = 'Date2Block:Thorchain'

    async def clear(self):
        r: Redis = await self.deps.db.get_redis()
        await r.delete(self.DB_KEY_DATE_TO_BLOCK_MAPPER)

    async def save_height_to_day_cache(self, day: date, block_height):
        if block_height is not None and block_height > 0:
            r: Redis = await self.deps.db.get_redis()
            await r.hset(self.DB_KEY_DATE_TO_BLOCK_MAPPER, day_to_key(day), block_height)

    async def load_height_from_day_cache(self, day) -> int:
        r: Redis = await self.deps.db.get_redis()
        data = await r.hget(self.DB_KEY_DATE_TO_BLOCK_MAPPER, day_to_key(day))
        return int(data) if data else None

    async def iterative_block_discovery_by_timestamp(self, ts: float, last_block=None, max_steps=10,
                                                     tolerance_sec=THOR_BLOCK_TIME * 1.5):
        if not last_block:
            last_block = await self.get_last_thorchain_block()

        now = datetime.now()
        total_seconds = now.timestamp() - ts
        assert total_seconds > 0

        estimated_block_height = last_block - total_seconds / THOR_BLOCK_TIME
        estimated_block_height = int(max(1, estimated_block_height))

        self.logger.info(f'Initial guess for {ts = } is #{estimated_block_height}')

        for step in range(max_steps):
            guess_ts = await self.get_timestamp_by_block_height(estimated_block_height)

            if guess_ts < 0:
                self.logger.warning(f'Probably there is no block #{estimated_block_height}.')
                # hard fork fallback
                return estimated_block_height

            seconds_diff = guess_ts - ts
            if abs(seconds_diff) <= tolerance_sec or estimated_block_height == 1:
                self.logger.info(f'Success. #{estimated_block_height = }!')
                break

            estimated_block_height -= seconds_diff / THOR_BLOCK_TIME
            estimated_block_height = int(max(1, estimated_block_height))

            self.logger.info(f'Step #{step + 1}. {estimated_block_height = }')

        return estimated_block_height

    async def calibrate(self, days=14, overwrite=False):
        last_block = await self.get_last_thorchain_block()

        today_beginning = days_ago_noon(0, hour=0)

        blocks = []

        for day_ago in range(days):
            that_day = today_beginning - timedelta(days=day_ago)

            if not overwrite:
                block_no = await self.load_height_from_day_cache(that_day)
                if block_no is not None:
                    blocks.append((that_day, block_no))
                    continue

            block_no = await self.iterative_block_discovery_by_timestamp(that_day.timestamp(), last_block,
                                                                         max_steps=self.iterative_algo_max_steps,
                                                                         tolerance_sec=self.iterative_algo_tolerance)
            self.logger.info(f'Writing date2block cache: {day_ago = }, {that_day = }, {block_no = }')

            await self.save_height_to_day_cache(that_day, block_no)

            blocks.append((that_day, block_no))

        return blocks

    async def get_block_height_by_date(self, d: date, last_block=None) -> int:
        cached_block = await self.load_height_from_day_cache(d)
        if cached_block is not None and cached_block > 0:
            return cached_block

        that_date = datetime(d.year, d.month, d.day)
        block = await self.iterative_block_discovery_by_timestamp(that_date.timestamp(), last_block=last_block,
                                                                  max_steps=self.iterative_algo_max_steps,
                                                                  tolerance_sec=self.iterative_algo_tolerance)

        await self.save_height_to_day_cache(d, block)
        return block
