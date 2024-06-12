import asyncio

from localization.eng_base import BaseLocalization
from services.jobs.fetch.trade_accounts import TradeAccountFetcher
from services.lib.texts import sep
from tools.lib.lp_common import LpAppFramework


async def demo_trade_balance(app: LpAppFramework):
    f: TradeAccountFetcher = app.deps.trade_acc_fetcher
    address = 'thor14mh37ua4vkyur0l5ra297a4la6tmf95mt96a55'
    balances = await f.get_whole_balances(address)
    print(balances)

    text = BaseLocalization.text_balances(balances)
    sep()
    print(text)
    await app.send_test_tg_message(text)
    sep()
    await asyncio.sleep(2.0)


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        await demo_trade_balance(app)


if __name__ == '__main__':
    asyncio.run(run())
