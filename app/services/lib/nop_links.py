import ujson

from services.lib.config import Config
from services.lib.db import DB
from services.lib.db_one2one import OneToOne
from services.lib.utils import class_logger, random_hex


class SettingsManager:
    TOKEN_LEN = 16

    KEY_MESSENGER = '_messenger'

    def __init__(self, db: DB, cfg: Config):
        self.db = db
        self.cfg = cfg
        self.public_url = cfg.as_str('web.public_url').rstrip('/')
        self.logger = class_logger(self)
        self.token_channel_db = OneToOne(db, 'Token-Channel')

    def get_link(self, token):
        return f'{self.public_url}/?token={token}'

    @staticmethod
    def db_key_settings(channel_id):
        return f'Settings:Data:{channel_id}'

    async def generate_new_token(self, channel_id: str):
        await self.revoke_token(channel_id)
        token = random_hex(self.TOKEN_LEN).decode()
        await self.token_channel_db.put(channel_id, token)
        return token

    async def revoke_token(self, channel_id: str):
        await self.token_channel_db.delete(channel_id)

    async def get_settings(self, channel_id: str):
        if not channel_id:
            return {}
        data = await self.db.redis.get(self.db_key_settings(channel_id))
        return ujson.loads(data) if data else {}

    async def get_settings_from_token(self, token: str):
        channel = await self.token_channel_db.get(token)
        return await self.get_settings(channel)

    async def set_settings(self, channel_id: str, settings):
        if not channel_id:
            return
        if not settings:
            await self.db.redis.delete(self.db_key_settings(channel_id))
        else:
            await self.db.redis.set(self.db_key_settings(channel_id), ujson.dumps(settings))

    def get_context(self, user_id):
        return SettingsContext(self, user_id)


class SettingsContext:
    def __init__(self, manager: SettingsManager, user_id):
        self.manager = manager
        self.user_id = user_id
        self._curr_settings = {}

    async def __aenter__(self):
        self._curr_settings = await self.manager.get_settings(self.user_id)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is None:
            await self.manager.set_settings(self.user_id, self._curr_settings)

    def __setitem__(self, key, item):
        self._curr_settings[key] = item

    def __getitem__(self, key):
        return self._curr_settings[key]

    def __repr__(self):
        return repr(self._curr_settings)

    def __len__(self):
        return len(self._curr_settings)

    def __delitem__(self, key):
        del self._curr_settings[key]
