import asyncio

from localization.languages import Language
from localization.manager import LocalizationManager
from services.dialog.picture.crypto_logo import CryptoLogoDownloader
from services.dialog.picture.resources import Resources
from services.dialog.picture.savers_picture import SaversPictureGenerator
from services.jobs.fetch.last_block import LastBlockFetcher
from services.notify.types.block_notify import LastBlockStore
from tools.lib.lp_common import LpAppFramework, save_and_show_pic


async def get_savers_pic(app):
    loc_man: LocalizationManager = app.deps.loc_man
    loc = loc_man.get_from_lang(Language.ENGLISH)

    pic_gen = SaversPictureGenerator(loc)
    return await pic_gen.get_picture()


async def demo_logo_download(app: LpAppFramework):
    logo_downloader = CryptoLogoDownloader(Resources().LOGO_BASE)

    assets = [
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
        logo = await logo_downloader.get_or_download_logo_cached(asset)



async def demo_show_savers_pic(app: LpAppFramework):
    pic, _ = await get_savers_pic(app)
    save_and_show_pic(pic, 'savers')


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        d = app.deps
        d.last_block_fetcher = LastBlockFetcher(d)
        d.last_block_store = LastBlockStore(d)
        await d.last_block_fetcher.run_once()
        await d.mimir_const_fetcher.fetch()  # get constants beforehand
        await app.deps.pool_fetcher.fetch()

        await demo_logo_download(app)


if __name__ == '__main__':
    asyncio.run(run())
