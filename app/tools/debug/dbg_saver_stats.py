import asyncio
import random

from localization.eng_base import BaseLocalization
from localization.languages import Language
from services.jobs.fetch.pool_price import PoolFetcher
from services.lib.date_utils import MINUTE
from services.lib.texts import sep
from services.notify.types.savers_stats_notify import SaversStatsNotifier, EventSaverStats
from tools.lib.lp_common import LpAppFramework


async def demo_collect_stat(app: LpAppFramework):
    pf: PoolFetcher = app.deps.pool_fetcher
    await app.deps.last_block_fetcher.run_once()
    pool_map = await pf.reload_global_pools()
    ssn = SaversStatsNotifier(app.deps)
    data = await ssn.get_all_savers(pool_map, app.deps.price_holder.usd_per_rune,
                                    app.deps.last_block_store.last_thor_block)
    await ssn.save_savers(data)
    print(data)

    p_data = await ssn.get_previous_saver_stats(0)
    print(p_data)
    assert data == p_data


async def demo_show_notification(app: LpAppFramework):
    ssn = SaversStatsNotifier(app.deps)
    c_data = await ssn.get_previous_saver_stats(0)

    if not c_data:
        print('No data! Run "demo_collect_stat" first.')
        return 'error'

    def r(x, scatter=0.2):
        return x * random.uniform(1.0 - scatter, 1.0 + scatter)

    p_data = c_data._replace(
        total_unique_savers=int(r(c_data.total_unique_savers))
    )
    p_data = p_data._replace(
        pools=[p._replace(
            arp=r(p.arp),
            total_asset_saved=r(p.total_asset_saved),
            total_asset_as_usd=r(p.total_asset_as_usd)
        ) for p in c_data.pools]
    )

    event = EventSaverStats(p_data, c_data)

    loc: BaseLocalization = app.deps.loc_man[Language.RUSSIAN]
    await app.send_test_tg_message(loc.notification_text_saver_stats(event))

    loc: BaseLocalization = app.deps.loc_man[Language.ENGLISH]
    await app.send_test_tg_message(loc.notification_text_saver_stats(event))

    sep()

    tw_loc: BaseLocalization = app.deps.loc_man[Language.ENGLISH_TWITTER]
    print(tw_loc.notification_text_saver_stats(event))


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        # await demo_collect_stat(app)
        if await demo_show_notification(app) == 'error':
            await demo_collect_stat(app)
            await demo_show_notification(app)


if __name__ == '__main__':
    asyncio.run(main())
