import json
from contextlib import suppress
from typing import Optional

from redis.asyncio import Redis

from services.jobs.scanner.swap_props import SwapProps
from services.lib.date_utils import DAY
from services.lib.db import DB
from services.lib.utils import WithLogger


class EventDatabase(WithLogger):
    def __init__(self, db: DB, expiration_sec=5 * DAY):
        super().__init__()
        self.db = db
        self._expiration_sec = expiration_sec

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
        if mapping:
            r: Redis = await self.db.get_redis()
            kwargs = {k: self._convert_type(v) for k, v in mapping.items()}

            key = self.key_to_tx(tx_id)

            await r.hset(key, mapping=kwargs)
            await r.expire(key, int(self._expiration_sec))

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
