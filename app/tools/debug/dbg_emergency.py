import asyncio

from tools.lib.lp_common import LpAppFramework


async def main():
    app = LpAppFramework
    async with app:
        er = app.deps.emergency
        asyncio.create_task(er.run_worker())

        await asyncio.sleep(1.0)

        er.report('test', 'Some test message', param=10, foo='bar', x=1e7)

        await asyncio.sleep(5.0)
        print('done!.')


if __name__ == '__main__':
    asyncio.run(main())
