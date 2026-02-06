from typing import List

from pydantic import BaseModel

from lib.date_utils import now_ts, format_time_ago
from lib.db import DB
from lib.logs import WithLogger


class FlagDescriptor(BaseModel):
    value: bool
    last_changed_ts: float
    last_access_ts: float
    full_path: str | None = None

    def access(self):
        self.last_access_ts = now_ts()

    def change_to(self, new_value: bool):
        if self.value != new_value:
            self.value = new_value
            self.last_changed_ts = now_ts()

    def __bool__(self):
        return self.value

    def __str__(self):
        n = now_ts()
        last_change = format_time_ago(n - self.last_changed_ts)
        last_access = format_time_ago(n - self.last_access_ts)
        return f'FlagDescriptor(value={self.value}, last_changed={last_change!r}, last_access_ts={last_access!r})'


class Flagship(WithLogger):
    def __init__(self, db: DB):
        super().__init__()
        self.db = db
        self.default_value = True

    DB_KEY_PREFIX = 'Flagship:'

    def key(self, flag_name: str) -> str:
        return f'{self.DB_KEY_PREFIX}{flag_name}'

    async def get_flag_object(self, flag_name: str) -> FlagDescriptor | None:
        if not self.db.redis:
            self.logger.warning('Redis is not available, assuming all flags are unset')
            return None

        if not flag_name:
            raise ValueError('Flag name cannot be empty')

        key = self.key(flag_name)
        json_data = await self.db.redis.get(key)
        if not json_data:
            return None

        try:
            data = FlagDescriptor.model_validate_json(json_data)
            return data
        except Exception as e:
            self.logger.error(f'Failed to parse flag data for "{flag_name}": {e}')
            return None

    async def save_flag_object(self, flag_name: str, flag: FlagDescriptor):
        if not self.db.redis:
            self.logger.warning('Redis is not available, cannot save flags')
            return

        if not flag_name:
            raise ValueError('Flag name cannot be empty')

        key = self.key(flag_name)
        json_data = flag.model_dump_json()
        await self.db.redis.set(key, json_data)

    async def is_flag_set(self, flag_name: str) -> bool:
        flag = await self.get_flag_object(flag_name)
        if flag:
            flag.access()
            await self.save_flag_object(flag_name, flag)
            return flag.value
        else:
            await self.set_flag(flag_name, self.default_value)
            return self.default_value

    async def set_flag(self, flag_name: str, value: bool):
        flag = await self.get_flag_object(flag_name)
        if not flag:
            flag = FlagDescriptor(value=value, last_changed_ts=now_ts(), last_access_ts=now_ts(),
                                  full_path=flag_name)
        else:
            flag.change_to(value)
        await self.save_flag_object(flag_name, flag)

    async def get_all(self) -> List[FlagDescriptor]:
        if not self.db.redis:
            self.logger.warning('Redis is not available, cannot retrieve flags')
            return []

        keys = await self.db.redis.keys(f'{self.DB_KEY_PREFIX}*')
        flags = []
        for key in keys:
            json_data = await self.db.redis.get(key)
            if json_data:
                try:
                    flag = FlagDescriptor.model_validate_json(json_data)
                    flags.append(flag)
                except Exception as e:
                    self.logger.error(f'Failed to parse flag data for key "{key}": {e}')
        return flags

    async def get_all_hierarchy(self) -> dict:
        if not self.db.redis:
            self.logger.warning('Redis is not available, cannot retrieve flags')
            return {}

        keys = await self.db.redis.keys(f'{self.DB_KEY_PREFIX}*')
        hierarchy = {}
        for key in keys:
            flag_name = key.replace(self.DB_KEY_PREFIX, '')
            parts = flag_name.split(':')
            current_level = hierarchy
            for part in parts[:-1]:
                if part not in current_level:
                    current_level[part] = {}
                current_level = current_level[part]
            current_level[parts[-1]] = await self.get_flag_object(flag_name)
        return hierarchy

    async def delete_flag(self, flag_name: str):
        if not self.db.redis:
            self.logger.warning('Redis is not available, cannot delete flags')
            return

        key = self.key(flag_name)
        await self.db.redis.delete(key)