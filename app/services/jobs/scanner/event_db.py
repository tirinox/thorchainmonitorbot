import json
from contextlib import suppress
from typing import Optional

from aioredis import Redis

from services.jobs.scanner.swap_props import SwapProps
from services.lib.db import DB
from services.lib.utils import WithLogger


class EventDatabase(WithLogger):
    def __init__(self, db: DB):
        super().__init__()
        self.db = db
        self.dbg_only_tx_id = None

    @staticmethod
    def key_to_tx(tx_id):
        return f'tx:tracker:{tx_id}'

    async def read_tx_status(self, tx_id) -> Optional[SwapProps]:
        r: Redis = await self.db.get_redis()
        props = await r.hgetall(self.key_to_tx(tx_id))
        return SwapProps.restore_events_from_tx_status(props)

    @staticmethod
    def _convert_type(v):
        if isinstance(v, bool):
            return 1 if v else 0
        elif isinstance(v, (int, float, str, bytes)):
            return v
        else:
            try:
                return json.dumps(v)
            except TypeError:
                return str(v)

    async def write_tx_status(self, tx_id, mapping):
        if self.dbg_only_tx_id and self.dbg_only_tx_id != tx_id:
            return

        if mapping:
            r: Redis = await self.db.get_redis()
            kwargs = {k: self._convert_type(v) for k, v in mapping.items()}
            await r.hset(self.key_to_tx(tx_id), mapping=kwargs)

    async def write_tx_status_kw(self, tx_id, **kwargs):
        await self.write_tx_status(tx_id, kwargs)

    @property
    def all_keys_pattern(self):
        return self.key_to_tx('*')

    async def load_all_keys(self):
        pattern = self.all_keys_pattern
        r: Redis = await self.db.get_redis()
        keys = await r.keys(pattern)
        return keys

    async def backup(self, filename):
        self.logger.info('Saving a backup')
        r: Redis = await self.db.get_redis()
        keys = await self.load_all_keys()

        local_db = {}
        for key in keys:
            props = await r.hgetall(key)
            local_db[key] = props

        with open(filename, 'w') as f:
            json.dump(local_db, f, indent=4)
            self.logger.info(f'Saved a backup containing {len(local_db)} records.')

    async def clean_up_old_events(self, before_block):
        keys = await self.load_all_keys()
        candidates_for_deletion = []
        r: Redis = await self.db.get_redis()
        for k in keys:
            height = await r.hget(k, 'block_height')
            if height:
                height = int(height)
                if height < before_block:
                    candidates_for_deletion.append(k)

        if candidates_for_deletion:
            self.logger.info(f'I will clean up {len(candidates_for_deletion)} TX records now.')
            await r.delete(*candidates_for_deletion)

    DB_KEY_SS_STARTED_SET = 'tx:ss-started-set'

    async def is_announced_as_started(self, tx_id: str) -> bool:
        if not tx_id:
            return True
        r: Redis = await self.db.get_redis()
        return await r.sismember(self.DB_KEY_SS_STARTED_SET, tx_id)

    async def announce_tx_started(self, tx_id: str):
        if tx_id:
            r: Redis = await self.db.get_redis()
            await r.sadd(self.DB_KEY_SS_STARTED_SET, tx_id)

    async def clear_tx_started_cache(self):
        with suppress(Exception):
            r: Redis = await self.db.get_redis()
            await r.delete(self.DB_KEY_SS_STARTED_SET)
