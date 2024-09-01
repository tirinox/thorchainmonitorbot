import asyncio
import dataclasses
import json
import random
from pprint import pprint

from localization.eng_base import BaseLocalization
from localization.languages import Language
from services.dialog.picture.crypto_logo import CryptoLogoDownloader
from services.dialog.picture.resources import Resources
from services.dialog.picture.savers_picture import SaversPictureGenerator
from services.jobs.fetch.savers_port import SaverStatsPortedFetcher
from services.jobs.fetch.savers_vnx import VNXSaversStatsFetcher
from services.lib.date_utils import DAY
from services.lib.texts import sep
from services.lib.utils import random_chance
from services.models.pool_info import PoolInfo
from services.models.savers import SaversBank, how_much_savings_you_can_add
from services.notify.types.savers_stats_notify import SaversStatsNotifier
from tools.lib.lp_common import LpAppFramework, save_and_show_pic


def randomize_savers_data(c_data: SaversBank, sc=0.2, fail_chance=0.3):
    def r(x, scatter=sc, no_change_chance=fail_chance):
        if random_chance(no_change_chance):
            return x
        return x * random.uniform(1.0 - scatter, 1.0 + scatter)

    p_data = dataclasses.replace(c_data,
                                 total_unique_savers=int(r(c_data.total_unique_savers, no_change_chance=0.1))
                                 )
    p_data.vaults = [dataclasses.replace(
        p,
        apr=r(p.apr),
        total_asset_saved=r(p.total_asset_saved),
        total_asset_saved_usd=r(p.total_asset_saved_usd),
        runes_earned=r(p.runes_earned),
        asset_cap=r(p.asset_cap),
        number_of_savers=int(r(p.number_of_savers)),
    ) for p in c_data.vaults]

    return p_data


async def demo_show_notification(app: LpAppFramework):
    await app.send_test_tg_message('----- S T A R T -----')

    ssn = SaversStatsNotifier(app.deps, None)

    event = await ssn.data_source.get_savers_event(period=DAY)

    loc: BaseLocalization = app.deps.loc_man[Language.RUSSIAN]
    await app.send_test_tg_message(loc.notification_text_saver_stats(event))

    loc: BaseLocalization = app.deps.loc_man[Language.ENGLISH]
    await app.send_test_tg_message(loc.notification_text_saver_stats(event))

    sep()

    tw_loc: BaseLocalization = app.deps.loc_man[Language.ENGLISH_TWITTER]
    print(tw_loc.notification_text_saver_stats(event))


async def demo_logo_download(app: LpAppFramework):
    logo_downloader = CryptoLogoDownloader(Resources().LOGO_BASE)

    assets = [
        'GAIA.ATOM',
        'BNB.AVA-645',
        'BNB.BCH-1FD',
        'BNB.BNB',
        'BNB.BTCB-1DE',
        'BNB.BUSD-BD1',
        'BNB.ETH-1C9',
        'BNB.TWT-8C2',
        'BNB.USDT-6D8',
        'BNB.XRP-BF2',
        'AVAX.USDC-0xa7d7079b0fead91f3e65f86e8915cb59c1a4c664'.upper(),
        'AVAX.AVAX',
        'DOGE.DOGE',
        'BCH.BCH',
        'BTC.BTC',
        'ETH.AAVE-0X7FC66500C84A76AD7E9C93437BFC5AC33E2DDAE9',
        'ETH.ALPHA-0XA1FAA113CBE53436DF28FF0AEE54275C13B40975',
        'ETH.ETH',
        'ETH.KYL-0X67B6D479C7BB412C54E03DCA8E1BC6740CE6B99C',
        'ETH.SNX-0XC011A73EE8576FB46F5E1C5751CA3B9FE0AF2A6F',
        'ETH.SUSHI-0X6B3595068778DD592E39A122F4F5A5CF09C90FE2',
        'ETH.THOR-0X3155BA85D5F96B2D030A4966AF206230E46849CB',
        'ETH.THOR-0XA5F2211B9B8170F694421F2046281775E8468044',
        'ETH.USDT-0X62E273709DA575835C7F6AEF4A31140CA5B1D190',
        'ETH.USDT-0XDAC17F958D2EE523A2206206994597C13D831EC7',
        'ETH.XRUNE-0X69FA0FEE221AD11012BAB0FDB45D444D3D2CE71C',
        'ETH.YFI-0X0BC529C00C6401AEF6D220BE8C6EA1667F6AD93E',
        'LTC.LTC',
    ]

    for asset in assets:
        await logo_downloader.get_or_download_logo_cached(asset)


async def demo_vnx(app: LpAppFramework):
    ssf = VNXSaversStatsFetcher(app.deps)
    vs = await ssf.load_real_yield_vanaheimex()
    r = ssf.make_bank(vs)
    pprint(r)


async def demo_show_savers_pic(app: LpAppFramework):
    await app.deps.pool_fetcher.run_once()
    await app.deps.last_block_fetcher.run_once()
    await app.deps.mimir_const_fetcher.run_once()

    # ssn = SaversStatsNotifier(app.deps, None)
    # event = await ssn.data_source.get_savers_event(7 * DAY)

    source = VNXSaversStatsFetcher(app.deps)
    event = await source.get_savers_event()

    loc = app.deps.loc_man[Language.ENGLISH]
    pic_gen = SaversPictureGenerator(loc, event)
    pic, name = await pic_gen.get_picture()

    print(name)

    save_and_show_pic(pic, 'savers-dynamic')


async def demo_new_method_to_reach_fullness(app: LpAppFramework):
    pools = await app.deps.pool_fetcher.load_pools()
    max_synth_per_pool_depth = app.deps.mimir_const_holder.get_max_synth_per_pool_depth()
    for pool in pools.values():
        pool: PoolInfo
        if not pool.savers_units:
            continue

        can_add = how_much_savings_you_can_add(pool, max_synth_per_pool_depth)
        print(f'{pool.asset} - {can_add} {pool.asset}')


async def dbg_new_saver_stats_fetcher(app: LpAppFramework):
    await app.deps.mimir_const_fetcher.run_once()
    ssf = SaverStatsPortedFetcher(app.deps)
    vs = await ssf.fetch()
    vs = {k: v._asdict() for k, v in vs.items()}
    print(json.dumps(vs, indent=4))

    input("Press enter to continue...")
    await ssf.fetch()
    print("Instant?")


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        await dbg_new_saver_stats_fetcher(app)
        # await app.deps.pool_fetcher.run_once()
        # await demo_show_savers_pic(app)
        # await demo_show_notification(app)
        # await demo_new_method_to_reach_fullness(app)
        # await demo_vnx(app)


if __name__ == '__main__':
    asyncio.run(main())
