import asyncio
import pprint

from comm.localization.eng_base import BaseLocalization
from jobs.fetch.pol import POLAndRunePoolFetcher
from jobs.scanner.native_scan import BlockScanner
from jobs.scanner.runepool import RunePoolEventDecoder
from lib.money import distort_randomly
from models.memo import THORMemo
from models.runepool import AlertRunePoolAction, AlertRunepoolStats, RunepoolState
from notify.public.runepool_notify import RunePoolTransactionNotifier, RunepoolStatsNotifier
from tools.lib.lp_common import LpAppFramework


WITHDRAW_TX_HASH = '6B27CC9346DF91559294DBDFD812D01E2FE79AFB18D6E5C0CD9EEED4C022AB77'
WITHDRAW_TX_HEIGHT = 18990272

DEPOSIT_TX_HASH = '0ABC436F8093EC56185E19B6338EF8C76051DD2B22D95DA94A27C8BC49343B3B'
DEPOSIT_TX_HEIGHT = 18961411

# DEPOSIT_TX_HEIGHT_2 = 17005268


async def demo_decode_runepool_deposit(app: LpAppFramework, height):

    scanner = BlockScanner(app.deps, role='debug')

    block = await scanner.fetch_one_block(height)

    decoder = RunePoolEventDecoder(app.deps.db, app.deps.pool_cache)
    r = await decoder.on_data(None, block)

    if not r:
        print('No runepool event found')
        return
    else:
        # print total
        print(f"Total found {len(r)} runepool txs")

    event: AlertRunePoolAction = r[0]
    pprint.pprint(event, width=1)

    name_map = await app.deps.name_service.safely_load_thornames_from_address_set(
        [event.actor, event.destination_address]
    )
    await app.test_all_locs(BaseLocalization.notification_runepool_action, None, event, name_map)


async def demo_simulate_withdrawal(app: LpAppFramework):
    event = AlertRunePoolAction(
        tx_hash='FA5EDC7CE67C61E19F2A7CEA500338248D082FC0D79E0829578DFF8E78D3607C',
        actor='thor166n4w5039meulfa3p6ydg60ve6ueac7tlt0jws',
        destination_address='thor166n4w5039meulfa3p6ydg60ve6ueac7tlt0jws',
        amount=123,
        usd_amount=123 * 4.5,
        is_deposit=False,
        height=16982896,
        memo=THORMemo.runepool_withdraw(3500, affiliate_address='t', affiliate_fee_bp=100)
    )

    name_map = await app.deps.name_service.safely_load_thornames_from_address_set(
        [event.actor, event.destination_address]
    )
    await app.test_all_locs(BaseLocalization.notification_runepool_action, None, event, name_map)


async def demo_simulate_deposit(app: LpAppFramework):
    event = AlertRunePoolAction(
        tx_hash='FA5EDC7CE67C61E19F2A7CEA500338248D082FC0D79E0829578DFF8E78D3607C',
        actor='thor166n4w5039meulfa3p6ydg60ve6ueac7tlt0jws',
        destination_address='thor166n4w5039meulfa3p6ydg60ve6ueac7tlt0jws',
        amount=123,
        usd_amount=123 * 4.5,
        is_deposit=True,
        height=16982896,
        memo=THORMemo.runepool_add()
    )
    name_map = await app.deps.name_service.safely_load_thornames_from_address_set(
        [event.actor, event.destination_address]
    )
    await app.test_all_locs(BaseLocalization.notification_runepool_action, None, event, name_map)

async def demo_runepool_continuous(app: LpAppFramework, b=0):
    d = app.deps
    d.block_scanner = BlockScanner(d, last_block=b, role='debug')
    d.block_scanner.one_block_per_run = b > 0

    runepool_decoder = RunePoolEventDecoder(d.db, d.pool_cache)
    d.block_scanner.add_subscriber(runepool_decoder)

    runepool_decoder.add_subscriber(d.volume_recorder)
    runepool_decoder.add_subscriber(d.tx_count_recorder)

    runepool_not = RunePoolTransactionNotifier(d)
    runepool_decoder.add_subscriber(runepool_not)
    runepool_not.add_subscriber(d.alert_presenter)

    runepool_decoder.sleep_period = 60
    runepool_decoder.initial_sleep = 0
    d.block_scanner.add_subscriber(runepool_decoder)

    await d.block_scanner.run()
    await asyncio.sleep(5.0)


async def demo_runepool_stats(app: LpAppFramework):
    await prepare_once(app)

    d = app.deps
    pol_fetcher = POLAndRunePoolFetcher(d)

    notifier = RunepoolStatsNotifier(d)
    # notifier.add_subscriber(d.alert_presenter)
    # pol_fetcher.add_subscriber(notifier)
    e = await pol_fetcher.fetch()

    previous: RunepoolState = await notifier.load_last_event()

    if not previous:
        previous = e.runepool
        await notifier.save_last_event(e.runepool)

    previous = previous._replace(
        pool=previous.pool._replace(
            providers=previous.pool.providers._replace(
                current_deposit=int(distort_randomly(previous.pool.providers.current_deposit, 15)),
                pnl=int(distort_randomly(previous.pool.providers.pnl, 10)),
            ),
            pol=previous.pool.pol._replace(
                current_deposit=int(distort_randomly(previous.pool.pol.current_deposit, 8)),
            )
        ),
        n_providers=int(distort_randomly(previous.n_providers, 30)),
        avg_deposit=distort_randomly(previous.avg_deposit, 10),
    )
    # previous = None

    usd_per_rune = await app.deps.pool_cache.get_usd_per_rune()

    new_event = AlertRunepoolStats(
        e.runepool,
        previous,
        usd_per_rune=usd_per_rune,
    )

    await app.test_all_locs(BaseLocalization.notification_runepool_stats, [
        # d.loc_man.default
    ], new_event)

    # await notifier.cd.clear()
    # await asyncio.sleep(5.0)


async def run():
    app = LpAppFramework()
    async with app:
        # await demo_decode_runepool_deposit(app, DEPOSIT_TX_HEIGHT)
        # await demo_decode_runepool_deposit(app, WITHDRAW_TX_HEIGHT)
        await demo_simulate_withdrawal(app)
        await demo_simulate_deposit(app)
        # await demo_runepool_continuous(app, b=DEPOSIT_TX_HEIGHT_1)
        # await demo_runepool_stats(app)


if __name__ == '__main__':
    asyncio.run(run())
