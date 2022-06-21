import asyncio

from localization.manager import LocalizationManager
from tools.lib.lp_common import LpAppFramework


async def run():
    app = LpAppFramework()
    await app.prepare()
    loc_man: LocalizationManager = app.deps.loc_man
    loc = loc_man.default
    texts = loc.text_mimir_info(app.deps.mimir_const_holder)
    for text in texts:
        print(text)


if __name__ == '__main__':
    asyncio.run(run())
