import asyncio
import logging

from localization.manager import BaseLocalization
from services.jobs.fetch.bep2_move import BEP2BlockFetcher, BinanceOrgDexWSSClient
from services.models.transfer import RuneTransfer
from services.notify.types.bep2_notify import BEP2MoveNotifier
from tools.lib.lp_common import LpAppFramework


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:
        await lp_app.prepare(brief=True)
        fetcher = BEP2BlockFetcher(lp_app.deps)
        notifier = BEP2MoveNotifier(lp_app.deps)
        fetcher.subscribe(notifier)
        # await fetcher.run()

        await not_format_test(lp_app)
        # await wss_dex_test(lp_app)


async def wss_dex_test(lp_app):
    wsc = BinanceOrgDexWSSClient()
    await wsc.listen_forever()


async def not_format_test(lp_app):
    loc: BaseLocalization = lp_app.deps.loc_man.default
    await lp_app.send_test_tg_message(loc.notification_text_bep2_movement(RuneTransfer(
        'bnb1dtpty6hrxehwz9xew6ttj52l929cu8zehprzwj',
        'bnb136ns6lfw4zs5hg4n85vdthaad7hq5m4gtkgf24', 0, '233232',
        100000, usd_per_asset=12.0
    )))

    loc: BaseLocalization = lp_app.deps.loc_man.get_from_lang('rus')
    await lp_app.send_test_tg_message(loc.notification_text_bep2_movement(RuneTransfer(
        'bnb1dtpty6hrxehwz9xew6ttj52l929cu8zehprzwj',
        'bnb136ns6lfw4zs5hg4n85vdthaad7hq5m4gtkgf24', 0, '233232',
        100000, usd_per_asset=12.0
    )))


if __name__ == '__main__':
    asyncio.run(main())
