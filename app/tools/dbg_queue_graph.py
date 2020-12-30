import asyncio
import os

from localization import LocalizationManager
from services.dialog.queue_picture import queue_graph
from services.lib.config import Config
from services.lib.db import DB
from services.lib.depcont import DepContainer


async def q_points(d: DepContainer):
    image = await queue_graph(d, d.loc_man.get_from_lang('rus'))
    p = os.path.expanduser('~/sns_test.png')
    with open(p, 'wb') as f:
        f.write(image.getvalue())
        os.system(f'open "{p}"')


async def stake_graph():
    ...


async def test_plots(d):
    # await q_points(d)
    await stake_graph()


if __name__ == '__main__':
    d = DepContainer()
    d.loc_man = LocalizationManager()
    d.loop = asyncio.get_event_loop()
    d.cfg = Config()
    d.db = DB(d.loop)

    d.loop.run_until_complete(test_plots(d))
