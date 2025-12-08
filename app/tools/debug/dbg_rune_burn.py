import asyncio
import json
from pprint import pprint

from jobs.fetch.mimir import ConstMimirFetcher
from jobs.rune_burn_recorder import RuneBurnRecorder
from lib.date_utils import HOUR, DAY
from lib.texts import sep
from lib.utils import namedtuple_to_dict
from models.mimir import MimirHolder
from models.mimir_naming import MIMIR_DICT_FILENAME
from tools.lib.lp_common import LpAppFramework


async def demo_last_burn_event(app: LpAppFramework, rec):
    event = await rec.get_event()
    # noinspection PyProtectedMember
    pprint(event._asdict())
    sep()
    print(json.dumps(namedtuple_to_dict(event), indent=2))
    sep()

    await app.deps.alert_presenter.on_data(None, event)
    await asyncio.sleep(10)


async def dbg_repopulate(app: LpAppFramework, rec: RuneBurnRecorder):
    period = HOUR / 2
    await rec.erase_and_populate_from_history(period=period, max_points=7 * DAY / period)


async def dbg_record_continuous(app: LpAppFramework, rec: RuneBurnRecorder):
    d = app.deps
    mimir_f = d.mimir_const_fetcher = ConstMimirFetcher(d)
    d.mimir_const_holder = MimirHolder()
    d.mimir_const_holder.mimir_rules.load(MIMIR_DICT_FILENAME)
    mimir_f.add_subscriber(d.mimir_const_holder)
    mimir_f.add_subscriber(rec)
    mimir_f.sleep_period = 5.0
    mimir_f.initial_sleep = 0.0
    await mimir_f.run()


async def run():
    app = LpAppFramework(log_level='INFO')
    async with app:
        rec = RuneBurnRecorder(app.deps)
        # await dbg_repopulate(app, rec)
        # await demo_burn_picture(app, rec)
        # await demo_last_burn_event(app, rec)
        await dbg_record_continuous(app, rec)


if __name__ == '__main__':
    asyncio.run(run())
