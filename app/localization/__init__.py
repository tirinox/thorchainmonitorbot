from services.lib.config import Config
from services.lib.db import DB
from localization.base import BaseLocalization
from localization.eng import EnglishLocalization
from localization.rus import RussianLocalization
from services.lib.utils import Singleton


class LocalizationManager(metaclass=Singleton):
    def __init__(self, cfg: Config):
        self.config = cfg
        self.default = EnglishLocalization(cfg)
        self._langs = {
            'rus': RussianLocalization(cfg),
            'eng': self.default
        }

    def get_from_lang(self, lang) -> BaseLocalization:
        return self._langs.get(str(lang), self.default)

    @staticmethod
    def lang_key(chat_id):
        return f'user:lang:{chat_id}'

    async def get_lang(self, chat_id, db: DB) -> str:
        redis = await db.get_redis()
        lang = await redis.get(self.lang_key(chat_id), encoding='utf-8')
        return lang if lang else None

    async def set_lang(self, chat_id, lang, db: DB):
        redis = await db.get_redis()
        await redis.set(self.lang_key(chat_id), str(lang))
        return await self.get_from_db(chat_id, db)

    async def get_from_db(self, chat_id, db: DB) -> BaseLocalization:
        lang = await self.get_lang(chat_id, db)
        return self.get_from_lang(lang)
