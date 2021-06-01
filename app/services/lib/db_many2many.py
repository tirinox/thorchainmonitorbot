from typing import List

from aioredis import Redis

from services.lib.db import DB


class ManyToManySet:
    def __init__(self, db: DB, left_prefix: str, right_prefix: str):
        self.db = db
        self.left_prefix = left_prefix
        self.right_prefix = right_prefix

    async def _redis(self) -> Redis:
        return await self.db.get_redis()

    def left_key(self, k):
        return f'set:{self.left_prefix}-2-{self.right_prefix}:{self.left_prefix}:{k}'

    def right_key(self, k):
        return f'set:{self.left_prefix}-2-{self.right_prefix}:{self.right_prefix}:{k}'

    async def clear(self):
        r = await self._redis()
        lefts = await r.keys(self.left_key('*'))
        rights = await r.keys(self.right_key('*'))
        keys = lefts + rights
        if keys:
            await r.delete(*keys)

    async def associate_many(self, lefts: List[str], rights: List[str]):
        r = await self._redis()
        if rights:
            for left_one in lefts:
                await r.sadd(self.left_key(left_one), *rights)
        if lefts:
            for right_one in rights:
                await r.sadd(self.right_key(right_one), *lefts)

    async def associate(self, left_one: str, right_one: str):
        await self.associate_many([left_one], [right_one])

    async def all_lefts(self, right_one: str):
        r = await self._redis()
        return set(await r.smembers(self.right_key(right_one), encoding='utf8'))

    async def all_rights(self, left_one: str):
        r = await self._redis()
        return set(await r.smembers(self.left_key(left_one), encoding='utf8'))

    # noinspection PyArgumentList
    async def remove_association(self, item: str, is_item_left: bool):
        r = await self._redis()

        getter = self.all_rights if is_item_left else self.all_lefts
        all_items = await getter(item)
        other_side_key = self.left_key(item) if is_item_left else self.right_key(item)
        await r.srem(other_side_key, *all_items)
        for other_item in all_items:
            this_side_key = self.right_key(other_item) if is_item_left else self.left_key(other_item)
            await r.srem(this_side_key, item)

    async def remove_all_rights(self, left_one: str):
        await self.remove_association(left_one, is_item_left=True)

    async def remove_all_lefts(self, right_one: str):
        await self.remove_association(right_one, is_item_left=False)
