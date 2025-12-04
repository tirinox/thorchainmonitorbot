import asyncio

from comm.localization.languages import Language
from tools.lib.lp_common import LpAppFramework


async def main():
    app = LpAppFramework()

    async with app:
        loc = app.deps.loc_man[Language.RUSSIAN]
        f = loc._conditional_announcement

        await app.send_test_tg_message(loc._announcement())

        for i in range(1, 11):
            print(f'{i}: {f()}')


if __name__ == '__main__':
    asyncio.run(main())
