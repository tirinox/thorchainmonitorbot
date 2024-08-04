import asyncio
import pprint

from localization.eng_base import BaseLocalization
from services.jobs.fetch.pol import RunePoolFetcher
from services.jobs.scanner.native_scan import NativeScannerBlock
from services.jobs.scanner.runepool import RunePoolEventDecoder
from services.jobs.volume_recorder import VolumeRecorder, TxCountRecorder
from services.lib.money import distort_randomly
from services.models.memo import THORMemo
from services.models.runepool import AlertRunePoolAction, AlertRunepoolStats, RunepoolState
from services.notify.types.runepool_notify import RunePoolTransactionNotifier, RunepoolStatsNotifier
from tools.lib.lp_common import LpAppFramework

prepared = False


async def prepare_once(app):
    global prepared
    if not prepared:
        d = app.deps
        d.block_scanner = NativeScannerBlock(d)

        d.volume_recorder = VolumeRecorder(d)
        d.tx_count_recorder = TxCountRecorder(d)

        await d.pool_fetcher.reload_global_pools()
        await d.last_block_fetcher.run_once()
        await d.mimir_const_fetcher.run_once()
        prepared = True


DEPOSIT_TX_HASH_1 = 'FA5EDC7CE67C61E19F2A7CEA500338248D082FC0D79E0829578DFF8E78D3607C'
DEPOSIT_TX_HEIGHT_1 = 16982896
DEPOSIT_TX_HEIGHT_2 = 17005268


async def demo_decode_runepool_deposit(app: LpAppFramework, height):
    await prepare_once(app)

    scanner = NativeScannerBlock(app.deps)

    block = await scanner.fetch_one_block(height)

    decoder = RunePoolEventDecoder(app.deps.db, app.deps.price_holder)
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
        memo=THORMemo.runepool_withdraw(3500, affiliate='t', affiliate_fee_bp=100)
    )

    name_map = await app.deps.name_service.safely_load_thornames_from_address_set(
        [event.actor, event.destination_address]
    )
    await app.test_all_locs(BaseLocalization.notification_runepool_action, None, event, name_map)


async def demo_runepool_continuous(app: LpAppFramework, b=0):
    await prepare_once(app)

    d = app.deps
    d.block_scanner = NativeScannerBlock(d, last_block=b)
    d.block_scanner.one_block_per_run = b > 0

    runepool_decoder = RunePoolEventDecoder(d.db, d.price_holder)
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
    runepool_fetcher = RunePoolFetcher(d)

    notifier = RunepoolStatsNotifier(d)
    # notifier.add_subscriber(d.alert_presenter)
    # runepool_fetcher.add_subscriber(notifier)
    e = await runepool_fetcher.fetch()

    previous: RunepoolState = await notifier.load_last_event()

    if not previous:
        previous = e.runepool
        await notifier._save_last_event(e.runepool)

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

    new_event = AlertRunepoolStats(
        e.runepool,
        previous,
        usd_per_rune=app.deps.price_holder.usd_per_rune,
    )

    await app.test_all_locs(BaseLocalization.notification_runepool_stats, [
        # d.loc_man.default
    ], new_event)

    # await notifier.cd.clear()
    # await runepool_fetcher.run_once()
    # await asyncio.sleep(5.0)


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        # await demo_decode_runepool_deposit(app, DEPOSIT_TX_HEIGHT_1)
        # await demo_decode_runepool_deposit(app, DEPOSIT_TX_HEIGHT_2)
        # await demo_simulate_withdrawal(app)
        # await demo_runepool_continuous(app, b=DEPOSIT_TX_HEIGHT_1)
        await demo_runepool_stats(app)


if __name__ == '__main__':
    asyncio.run(run())
