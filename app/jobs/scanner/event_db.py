import asyncio
import json
import re
from typing import Optional

from redis.asyncio import Redis

from jobs.scanner.swap_props import SwapProps
from lib.date_utils import DAY
from lib.db import DB
from lib.logs import WithLogger
from models.tx import ThorAction


class EventDatabase(WithLogger):
    def __init__(self, db: DB, expiration_sec=5 * DAY):
        super().__init__()
        self.db = db
        self._expiration_sec = expiration_sec

    @staticmethod
    def key_to_tx(tx_id):
        return f'tx:tracker:{tx_id}'

    @staticmethod
    def normalize_flag_name(flag_name: str) -> str:
        flag_name = re.sub(r'[^a-z0-9_]+', '_', str(flag_name or '').strip().lower()).strip('_')
        if not flag_name:
            raise ValueError('flag_name must not be empty')
        return flag_name

    @classmethod
    def component_flag_name(cls, component_name: str) -> str:
        component_name = cls.normalize_flag_name(component_name)
        if component_name.startswith('seen_'):
            return component_name
        return f'seen_{component_name}'

    @staticmethod
    def _as_bool(value) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0

        value = str(value).strip().lower()
        return value not in ('', '0', 'false', 'none', 'null', 'no')

    async def read_tx_status(self, tx_id) -> Optional[SwapProps]:
        r: Redis = await self.db.get_redis()
        props = await r.hgetall(self.key_to_tx(tx_id))
        return SwapProps.restore_events_from_tx_status(props)

    async def has_tx_flag(self, tx_id, flag_name: str) -> bool:
        if not tx_id:
            return False

        r: Redis = await self.db.get_redis()
        flag_name = self.normalize_flag_name(flag_name)
        value = await r.hget(self.key_to_tx(tx_id), flag_name)
        return self._as_bool(value)

    async def set_tx_flag(self, tx_id, flag_name: str, value=True):
        if not tx_id:
            return
        await self.write_tx_status(tx_id, {
            self.normalize_flag_name(flag_name): value,
        })

    async def is_component_seen(self, tx_id, component_name: str) -> bool:
        return await self.has_tx_flag(tx_id, self.component_flag_name(component_name))

    async def mark_component_as_seen(self, tx_id, component_name: str, value=True):
        await self.set_tx_flag(tx_id, self.component_flag_name(component_name), value=value)

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

            # print(f"{tx_id}: {mapping}")

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

    async def erase_tx_id(self, tx_id):
        r: Redis = await self.db.get_redis()
        key = self.key_to_tx(tx_id)
        await r.delete(key)
        self.logger.warning(f'Erased tx_id {tx_id} from the database.')


class EventDbTxDeduplicator:
    """
    Small EventDatabase-backed deduplicator.

    Instead of a separate bloom filter keyspace, it stores a per-component
    seen-flag directly inside the existing `tx:tracker:{tx_id}` hash.
    """

    def __init__(self, db: DB, component_name: str, *args, ignore_all_checks=False, **kwargs):
        self.event_db = EventDatabase(db)
        self.component_name = component_name
        self.flag_name = self.event_db.component_flag_name(component_name)
        self.ignore_all_checks = bool(ignore_all_checks)

    @property
    def key(self):
        return self.flag_name

    def __repr__(self):
        return f'<EventDbTxDeduplicator flag={self.flag_name}>'

    async def have_ever_seen(self, tx: ThorAction):
        if not tx or not tx.tx_hash:
            return True
        return await self.have_ever_seen_hash(tx.tx_hash)

    async def have_ever_seen_hash(self, tx_id) -> bool:
        if self.ignore_all_checks and tx_id:
            return False
        return await self.event_db.has_tx_flag(tx_id, self.flag_name)

    async def mark_as_seen(self, tx_id):
        if self.ignore_all_checks:
            return
        await self.event_db.set_tx_flag(tx_id, self.flag_name, True)

    async def mark_as_seen_txs(self, txs: list[ThorAction]):
        if self.ignore_all_checks:
            return
        for tx in txs:
            if tx and tx.tx_hash:
                await self.mark_as_seen(tx.tx_hash)

    async def batch_ever_seen_hashes(self, txs: list[str]):
        return await asyncio.gather(*[self.have_ever_seen_hash(tx_hash) for tx_hash in txs])

    async def only_hashes_having_certain_flag(self, txs: list[str], desired_flag) -> list[str]:
        flags = await self.batch_ever_seen_hashes(txs)
        desired_flag = bool(desired_flag)
        return [tx_id for flag, tx_id in zip(flags, txs) if bool(flag) == desired_flag]

    async def only_txs_having_certain_flag(self, txs: list[ThorAction], desired_flag) -> list[ThorAction]:
        tx_dict = {tx.tx_hash: tx for tx in txs if tx and tx.tx_hash}
        filtered_tx_hashes = set(await self.only_hashes_having_certain_flag(list(tx_dict.keys()), desired_flag))
        return [tx for tx in tx_dict.values() if tx.tx_hash in filtered_tx_hashes]

    async def only_new_hashes(self, txs: list[str]) -> list[str]:
        return await self.only_hashes_having_certain_flag(txs, False)

    async def only_seen_hashes(self, txs: list[str]) -> list[str]:
        return await self.only_hashes_having_certain_flag(txs, True)

    async def only_new_txs(self, txs: list[ThorAction], logs=False) -> list[ThorAction]:
        len_in = len(txs)
        results = await self.only_txs_having_certain_flag(txs, False)
        if logs and len(results) != len_in:
            self.event_db.logger.info(f'(flag={self.flag_name}) Filtered {len_in} txs to {len(results)} new txs.')
        return results

    async def only_seen_txs(self, txs: list[ThorAction]) -> list[ThorAction]:
        return await self.only_txs_having_certain_flag(txs, True)

