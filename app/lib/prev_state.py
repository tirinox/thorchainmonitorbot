import dataclasses
import json

from lib.db import DB
from lib.logs import WithLogger
from lib.utils import is_named_tuple_instance, namedtuple_to_dict


class PrevStateDB(WithLogger):
    def __init__(self, db: DB, data_type: type, prefix_key: str = ''):
        super().__init__()
        self.db = db
        self.data_type = data_type
        self.prefix_key = prefix_key or data_type.__name__
        self.last_exception: Exception | None = None

    @property
    def db_key(self):
        return f"{self.prefix_key}:PrevState"

    async def get(self):
        r = await self.db.get_redis()
        raw_data = await r.get(self.db_key)
        if raw_data is not None:
            self.logger.debug(f"Loaded previous state from DB with key '{self.db_key}'")
            try:
                data = json.loads(raw_data)
                if hasattr(self.data_type, 'from_json') and callable(getattr(self.data_type, 'from_json')):
                    return self.data_type.from_json(data)
                else:
                    return self.data_type(**data)
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to decode previous state JSON: {e}")
                self.last_exception = e
                return None
            except TypeError as e:
                self.logger.error(f"Failed to construct data_type from JSON: {e}")
                self.last_exception = e
                return None

        return raw_data

    async def set(self, data):
        try:
            if hasattr(data, 'to_dict'):
                dict_data = data.to_dict()
            elif is_named_tuple_instance(data):
                dict_data = namedtuple_to_dict(data)
            elif dataclasses.is_dataclass(data):
                dict_data = dataclasses.asdict(data)
            else:
                dict_data = data

            raw_data = json.dumps(dict_data)

            r = await self.db.get_redis()

            await r.set(self.db_key, raw_data)
            self.logger.debug(f"Saved previous state to DB with key '{self.db_key}'")
        except Exception as e:
            self.logger.error(f"Failed to save previous state to DB: {e}")
            self.last_exception = e
