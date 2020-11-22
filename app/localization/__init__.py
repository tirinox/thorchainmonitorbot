from services.lib.db import DB
from localization.base import BaseLocalization
from localization.eng import EnglishLocalization
from localization.rus import RussianLocalization


class LocalizationManager:
    def __init__(self):
        self._langs = {
            'rus': RussianLocalization(),
            'eng': EnglishLocalization()
        }
        self.default = EnglishLocalization()

    def get_from_lang(self, lang):
        return self._langs.get(str(lang), self.default)

    @staticmethod
    def lang_key(chat_id):
        return f'user:lang:{chat_id}'

    async def get_lang(self, chat_id, db: DB):
        redis = await db.get_redis()
        lang = await redis.get(self.lang_key(chat_id))
        return lang.decode() if lang else None

    async def set_lang(self, chat_id, lang, db: DB):
        redis = await db.get_redis()
        await redis.set(self.lang_key(chat_id), str(lang))

    async def get_from_db(self, chat_id, db: DB):
        lang = await self.get_lang(chat_id, db)
        return self.get_from_lang(lang)
