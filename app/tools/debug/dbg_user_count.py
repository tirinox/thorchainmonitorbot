import asyncio
import logging

from aioredis import Redis

from tools.lib.lp_common import LpAppFramework


async def benchmark_accuracy_of_hyper_log_log(lp_app: LpAppFramework):
    k = 'TestHyperLogLog'
    n = 100000
    r: Redis = await lp_app.deps.db.get_redis()
    await r.delete(k)
    for i in range(n):
        await r.pfadd(k, f'user{i}')
    r_n = await r.pfcount(k)
    print(f'{n = }, {r_n = }.')


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app(brief=True):
        await benchmark_accuracy_of_hyper_log_log(lp_app)


if __name__ == '__main__':
    asyncio.run(main())
