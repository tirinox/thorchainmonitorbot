import asyncio
import pprint

from comm.localization.eng_base import BaseLocalization
from jobs.fetch.trade_accounts import TradeAccountFetcher
from jobs.scanner.native_scan import BlockScanner
from jobs.scanner.trade_acc import TradeAccEventDecoder
from lib.texts import sep
from lib.utils import load_pickle, save_pickle
from models.trade_acc import AlertTradeAccountAction
from notify.public.trade_acc_notify import TradeAccSummaryNotifier, TradeAccTransactionNotifier
from tools.lib.lp_common import LpAppFramework

prepared = False


async def prepare_once(app):
    global prepared
    if not prepared:
        await app.deps.pool_fetcher.run_once()
        await app.deps.last_block_fetcher.run_once()
        await app.deps.mimir_const_fetcher.run_once()
        prepared = True


async def demo_trade_balance(app: LpAppFramework):
    await prepare_once(app)

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


TX_ID_DEPOSIT_USDC = "B30F34A6168F4C1282C3762C0E6CDE50B541ADE849F0770BE36DFE517AF0A71C"

TX_ID_WITHDRAWAL = "8F61556AC39FD3EC6C79D3F00B3D47E1AB62F0879B74FF63B6AE2E1EFF6F7978"

TX_WITHDRAW_USDC = '4466C745450161E0B8BE30D0429267E88CE0BAB7BBF5310734990CB7AEFC9414'

TX_ID_DEPOSIT_BTC = '442371c470efb32c1d91651889da5af900306dcff43cfdbf678d56ce2a84be2b'



async def demo_decode_trade_acc(app: LpAppFramework, tx_id):
    await prepare_once(app)

    scanner = BlockScanner(app.deps)

    tx = await app.deps.thor_connector.query_tx_details(tx_id)
    height = tx['consensus_height']

    block = await scanner.fetch_one_block(height)

    dcd = TradeAccEventDecoder(app.deps.price_holder)
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


async def demo_trade_acc_decode_continuous(app: LpAppFramework, b=0):
    await prepare_once(app)

    d = app.deps
    scanner = BlockScanner(d, last_block=b)
    # scanner.one_block_per_run = b > 0

    dcd = TradeAccEventDecoder(d.price_holder)
    dcd.sleep_period = 60
    dcd.initial_sleep = 0
    scanner.add_subscriber(dcd)

    nt = TradeAccTransactionNotifier(d)
    nt.cd.max_times = 1000
    await nt.reset()
    nt.min_usd_amount = 0.0
    dcd.add_subscriber(nt)
    nt.add_subscriber(d.alert_presenter)

    # achievements = AchievementsNotifier(d)
    # dcd.add_subscriber(achievements)

    await scanner.run()
    await asyncio.sleep(5.0)


async def demo_top_trade_asset_holders(app: LpAppFramework):
    await prepare_once(app)

    f: TradeAccountFetcher = app.deps.trade_acc_fetcher
    r = await f.fetch()
    print(r)


async def demo_trade_acc_summary_continuous(app: LpAppFramework):
    await prepare_once(app)

    d = app.deps
    trade_acc_fetcher = TradeAccountFetcher(d)
    trade_acc_fetcher.sleep_period = 60
    trade_acc_fetcher.initial_sleep = 0

    tr_acc_summary_not = TradeAccSummaryNotifier(d)
    tr_acc_summary_not.add_subscriber(d.alert_presenter)
    trade_acc_fetcher.add_subscriber(tr_acc_summary_not)

    # d.trade_acc_fetcher.add_subscriber(achievements)

    await trade_acc_fetcher.run()


async def demo_trade_acc_summary_single(app: LpAppFramework, reset_cache=False):
    d = app.deps

    trade_acc_fetcher = TradeAccountFetcher(d)

    tr_acc_summary_not = TradeAccSummaryNotifier(d)
    tr_acc_summary_not.add_subscriber(d.alert_presenter)
    trade_acc_fetcher.add_subscriber(tr_acc_summary_not)
    # d.trade_acc_fetcher.add_subscriber(achievements)

    cache_path = '../temp/trade_acc_summary_v4.pickle'
    data = None if reset_cache else load_pickle(cache_path)
    if not data:
        await prepare_once(app)
        data = await trade_acc_fetcher.fetch()
        save_pickle(cache_path, data)

    # fixme
    # data: AlertTradeAccountStats = data._replace(
    #     swaps_prev= int(distort_randomly(data.swaps_current, 30)),
    #     swap_vol_prev_usd= distort_randomly(data.swap_vol_current_usd, 30),
    # )

    if data:
        sep()
        print(data)
        sep()
        locs = None
        # locs = [
        #     app.deps.loc_man[Language.ENGLISH]
        # ]
        await app.test_all_locs(BaseLocalization.notification_text_trade_account_summary, locs, data)
    else:
        print('No data!')


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        # await demo_trade_balance(app)
        # await demo_decode_trade_acc(app, TX_WITHDRAW_USDC)
        # await demo_decode_trade_acc(app, TX_ID_DEPOSIT_USDC)
        # sep()
        # await demo_decode_trade_acc(app, TX_ID_WITHDRAWAL)
        # sep()
        # await demo_decode_trade_acc(app, TX_WITHDRAW_USDT)
        # sep()

        # await demo_top_trade_asset_holders(app)

        # await demo_trade_acc_summary_continuous(app)
        # await demo_trade_acc_summary_single(app, reset_cache=False)
        # await demo_trade_acc_decode_continuous(app, 19973890)
        await demo_trade_acc_decode_continuous(app, 20950594 - 1000)


if __name__ == '__main__':
    asyncio.run(run())
