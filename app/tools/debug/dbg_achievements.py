import asyncio

from tools.lib.lp_common import LpAppFramework


async def demo_show_notification(app: LpAppFramework):
    ...


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        await demo_show_notification(app)


if __name__ == '__main__':
    asyncio.run(main())
