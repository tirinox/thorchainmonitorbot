import asyncio
import pprint

from localization.eng_base import BaseLocalization
from services.jobs.fetch.trade_accounts import TradeAccountFetcher
from services.jobs.scanner.native_scan import NativeScannerBlock
from services.jobs.scanner.trade_acc import TradeAccEventDecoder
from services.lib.texts import sep
from services.models.trade_acc import AlertTradeAccountAction
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


TX_ID_DEPOSIT = "9699628842381c43f413fd004ac5b6679e682cecc46a95b45fa28998ea1fee2e"
TX_DEPOSIT_BLOCK_HEIGHT = 16391695
TX_ID_WITHDRAWAL = "8F61556AC39FD3EC6C79D3F00B3D47E1AB62F0879B74FF63B6AE2E1EFF6F7978"
TX_WITHDRAWAL_BLOCK_HEIGHT = 16389279

TX_WITHDRAW_USDT = '5CADA8C13A6CAC009F1B3653979F17CBAB8BAC416D2DB8E265EE8CE73C4366F6'
TX_WITHDRAW_USDT_BLOCK_HEIGHT = 16469565

TX_ID_DEPOSIT_BTC = '442371c470efb32c1d91651889da5af900306dcff43cfdbf678d56ce2a84be2b'
TX_DEPOSIT_BTC_BLOCK_HEIGHT = 16485260

BLOCK_MAP = {
    TX_ID_DEPOSIT: TX_DEPOSIT_BLOCK_HEIGHT,
    TX_ID_WITHDRAWAL: TX_WITHDRAWAL_BLOCK_HEIGHT,
    TX_WITHDRAW_USDT: TX_WITHDRAW_USDT_BLOCK_HEIGHT,
    TX_ID_DEPOSIT_BTC: TX_DEPOSIT_BTC_BLOCK_HEIGHT,
}


async def demo_decode_trade_acc(app: LpAppFramework, tx_id):
    scanner = NativeScannerBlock(app.deps)

    height = BLOCK_MAP[tx_id]
    block = await scanner.fetch_one_block(height)

    dcd = TradeAccEventDecoder(app.deps.db, app.deps.price_holder)
    r = await dcd.on_data(None, block)

    if not r:
        print('No trade acc event found')
        return
    else:
        # print total
        print(f"Total found {len(r)} txs")

    event: AlertTradeAccountAction = r[0]
    pprint.pprint(event, width=1)

    name_map = await app.deps.name_service.safely_load_thornames_from_address_set(
        [event.actor, event.destination_address]
    )
    await app.test_all_locs(BaseLocalization.notification_text_trade_account_move, None, event, name_map)


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        await app.deps.pool_fetcher.reload_global_pools()
        await app.deps.last_block_fetcher.run_once()
        await app.deps.mimir_const_fetcher.run_once()

        # await demo_trade_balance(app)
        await demo_decode_trade_acc(app, TX_ID_DEPOSIT_BTC)
        sep()
        await demo_decode_trade_acc(app, TX_ID_WITHDRAWAL)
        sep()

        # await demo_decode_trade_acc(app, TX_WITHDRAW_USDT)
        # sep()


if __name__ == '__main__':
    asyncio.run(run())
