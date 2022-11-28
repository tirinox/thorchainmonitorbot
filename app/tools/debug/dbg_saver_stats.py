import asyncio
import random

from localization.eng_base import BaseLocalization
from localization.languages import Language
from localization.manager import LocalizationManager
from services.dialog.picture.crypto_logo import CryptoLogoDownloader
from services.dialog.picture.resources import Resources
from services.dialog.picture.savers_picture import SaversPictureGenerator
from services.jobs.fetch.pool_price import PoolFetcher
from services.lib.texts import sep
from services.notify.types.savers_stats_notify import SaversStatsNotifier, EventSaverStats, AllSavers
from tools.lib.lp_common import LpAppFramework, save_and_show_pic


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


def randomize_savers_data(c_data: AllSavers, sc=0.2, fail_chance=0.3):
    def r(x, scatter=sc, no_change_chance=fail_chance):
        if random.uniform(0, 1) < no_change_chance:
            return x
        return x * random.uniform(1.0 - scatter, 1.0 + scatter)

    p_data = c_data._replace(
        total_unique_savers=int(r(c_data.total_unique_savers))
    )
    p_data = p_data._replace(
        pools=[p._replace(
            apr=r(p.apr),
            total_asset_saved=r(p.total_asset_saved),
            total_asset_as_usd=r(p.total_asset_as_usd),
            runes_earned=r(p.runes_earned),
            asset_cap=r(p.asset_cap),
            number_of_savers=int(r(p.number_of_savers)),
        ) for p in c_data.pools]
    )
    return p_data


async def demo_show_notification(app: LpAppFramework):
    await app.send_test_tg_message('----- S T A R T -----')

    ssn = SaversStatsNotifier(app.deps)
    c_data = await ssn.get_previous_saver_stats(0)

    if not c_data:
        print('No data! Run "demo_collect_stat" first.')
        return 'error'

    p_data = randomize_savers_data(c_data, fail_chance=0.0)

    event = EventSaverStats(p_data, c_data, 1.2)

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


async def demo_show_savers_pic(app: LpAppFramework):
    ssn = SaversStatsNotifier(app.deps)
    c_data = await ssn.get_previous_saver_stats(0)

    if not c_data:
        print('No data! Run "demo_collect_stat" first.')
        return 'error'

    loc_man: LocalizationManager = app.deps.loc_man
    loc = loc_man.get_from_lang(Language.ENGLISH)

    p_data = randomize_savers_data(c_data, fail_chance=0.8)
    # p_data = None

    pic_gen = SaversPictureGenerator(loc, EventSaverStats(
        p_data, c_data, app.deps.price_holder.usd_per_rune
    ), pool_map=app.deps.price_holder.pool_info_map)
    pic, name = await pic_gen.get_picture()

    print(name)

    save_and_show_pic(pic, 'savers')


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        await app.deps.pool_fetcher.run_once()
        await demo_collect_stat(app)
        await demo_show_savers_pic(app)
        # await demo_show_notification(app)


if __name__ == '__main__':
    asyncio.run(main())
