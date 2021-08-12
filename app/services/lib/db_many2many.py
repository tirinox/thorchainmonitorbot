import asyncio
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

    async def all_lefts_for_right_one(self, right_one: str):
        r = await self._redis()
        return set(await r.smembers(self.right_key(right_one), encoding='utf8'))

    async def all_items_for_many_other_side(self, inputs, getter: callable):
        inputs = set(inputs)
        groups = await asyncio.gather(
            *(getter(item) for item in inputs)
        )
        # flatten
        return set(item for group in groups for item in group)

    async def all_lefts_for_many_rights(self, rights: iter):
        return await self.all_items_for_many_other_side(rights, self.all_lefts_for_right_one)

    async def all_rights_for_many_lefts(self, lefts: iter):
        return await self.all_items_for_many_other_side(lefts, self.all_rights_for_left_one)

    async def all_rights_for_left_one(self, left_one: str):
        r = await self._redis()
        return set(await r.smembers(self.left_key(left_one), encoding='utf8'))

    async def all_from_side(self, key_gen):
        r = await self._redis()
        key_pattern = key_gen('*')
        start_pos = len(key_pattern) - 1
        names = await r.keys(key_pattern)
        return set(n.decode('utf-8')[start_pos:] for n in names)

    async def all_lefts(self):
        return await self.all_from_side(key_gen=self.left_key)

    async def all_rights(self):
        return await self.all_from_side(key_gen=self.right_key)

    async def all_right(self):
        r = await self._redis()
        lefts = await r.keys(self.left_key('*'))
        results = []
        for left_one in lefts:
            results += await r.smembers(left_one)
        return results

    # noinspection PyArgumentList
    async def remove_association(self, item: str, is_item_left: bool):
        r = await self._redis()

        getter = self.all_rights_for_left_one if is_item_left else self.all_lefts_for_right_one
        all_items = await getter(item)
        other_side_key = self.left_key(item) if is_item_left else self.right_key(item)
        await r.srem(other_side_key, *all_items)
        for other_item in all_items:
            this_side_key = self.right_key(other_item) if is_item_left else self.left_key(other_item)
            await r.srem(this_side_key, item)

    async def remove_one_item(self, left_item, right_item):
        r = await self._redis()
        await r.srem(self.left_key(left_item), right_item)
        await r.srem(self.right_key(right_item), left_item)

    async def remove_all_rights(self, left_one: str):
        await self.remove_association(left_one, is_item_left=True)

    async def remove_all_lefts(self, right_one: str):
        await self.remove_association(right_one, is_item_left=False)
