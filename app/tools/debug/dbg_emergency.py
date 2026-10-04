import asyncio

from tools.lib.lp_common import LpAppFramework


async def main():
    app = LpAppFramework()
    async with app:
        er = app.deps.emergency

        await asyncio.sleep(1.0)

        try:
            1 / 0
        except ZeroDivisionError:
            er.report('test', 'Some test message', param=10, foo='bar', x=1e7)
        er.report('test', 'Some test message')  # muted as a repeat

        await asyncio.sleep(5.0)
        print('done!.')


if __name__ == '__main__':
    asyncio.run(main())
