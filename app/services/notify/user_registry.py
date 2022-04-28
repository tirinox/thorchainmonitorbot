from services.lib.db import DB


class UserRegistry:
    def __init__(self, db: DB):
        self.db = db

    KEY_USERS = 'Bot:Users'

    async def register_user(self, chat_id):
        chat_id = str(int(chat_id))
        r = await self.db.get_redis()
        await r.sadd(self.KEY_USERS, chat_id)

    async def remove_users(self, idents):
        idents = [str(int(i)) for i in idents]
        if idents:
            r = await self.db.get_redis()
            await r.srem(self.KEY_USERS, *idents)

    async def all_users(self):
        r = await self.db.get_redis()
        items = await r.smembers(self.KEY_USERS)
        return [int(it) for it in items]
