import asyncio

from tools.lib.lp_common import LpAppFramework


async def migrate(redis, prefix):
    async for key in redis.scan_iter(match=f"{prefix}*"):
        new_key = key.replace(".", ":")
        if new_key != key:
            # rename is atomic (will overwrite if new_key exists)
            await redis.rename(key, new_key)
            print(f"Renamed {key} -> {new_key}")


async def main():
    app = LpAppFramework()
    async with app:
        r = await app.deps.db.get_redis()
        await migrate(r, 'THORNode')


if __name__ == '__main__':
    asyncio.run(main())
