from localization.eng_base import EnglishLocalization, BaseLocalization
from localization.languages import Language
from localization.rus import RussianLocalization
from localization.twitter_eng import TwitterEnglishLocalization
from services.lib.config import Config
from services.lib.db import DB
from services.lib.utils import Singleton


class LocalizationManager(metaclass=Singleton):
    def __init__(self, cfg: Config):
        self.config = cfg
        self.default = EnglishLocalization(cfg)
        self._langs = {
            Language.RUSSIAN: RussianLocalization(cfg),
            Language.ENGLISH: self.default,
            Language.ENGLISH_TWITTER: TwitterEnglishLocalization(cfg),
        }

    def __getitem__(self, item):
        return self.get_from_lang(item)

    def get_from_lang(self, lang) -> BaseLocalization:
        return self._langs.get(str(lang), self.default)

    def set_name_service(self, ns):
        for loc in self._langs.values():
            loc: BaseLocalization
            loc.name_service = ns

    @staticmethod
    def lang_key(chat_id):
        return f'user:lang:{chat_id}'

    async def get_lang(self, chat_id, db: DB) -> str:
        redis = await db.get_redis()
        lang = await redis.get(self.lang_key(chat_id))
        return lang if lang else None

    async def set_lang(self, chat_id, lang, db: DB):
        redis = await db.get_redis()
        await redis.set(self.lang_key(chat_id), str(lang))
        return await self.get_from_db(chat_id, db)

    async def get_from_db(self, chat_id, db: DB) -> BaseLocalization:
        lang = await self.get_lang(chat_id, db)
        return self.get_from_lang(lang)
