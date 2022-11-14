import asyncio
import os
from typing import List

from web3 import Web3

from localization.eng_base import BaseLocalization
from localization.languages import Language
from services.jobs.fetch.tx import TxFetcher
from services.jobs.volume_filler import VolumeFillerUpdater
from services.lib.constants import Chains, ETH_SYMBOL, AVAX_SYMBOL
from services.lib.date_utils import DAY
from services.lib.delegates import WithDelegates, INotified
from services.lib.money import DepthCurve
from services.lib.texts import sep
from services.lib.w3.aggregator import AggregatorDataExtractor
from services.lib.w3.dex_analytics import DexAnalyticsCollector
from services.lib.w3.erc20_contract import ERC20Contract
from services.lib.w3.router_contract import TCRouterContract
from services.lib.w3.token_list import TokenListCached, StaticTokenList
from services.models.tx import ThorTx, ThorTxType
from services.notify.types.tx_notify import SwapTxNotifier
from tools.lib.lp_common import LpAppFramework


async def get_abi(app: LpAppFramework, contract):
    api_key = app.deps.cfg.get('thor.circulating_supply.ether_scan_key')
    url = f'https://api.etherscan.io/api?module=contract&action=getabi&address={contract}&apikey={api_key}'
    print(url)
    async with app.deps.session.get(url) as reps:
        j = await reps.json()
        return j.get('result') if j.get('status') else None


async def my_test_erc20(w3):
    token = ERC20Contract(w3, '0x584bc13c7d411c00c01a62e8019472de68768430', chain_id=Chains.web3_chain_id(Chains.ETH))
    info = await token.get_token_info()
    print(info)


async def demo_process_events(w3):
    router = TCRouterContract(w3)

    # how to process events:
    receipt = await w3.get_transaction_receipt('0xD45F100F3F48C786720167F5705B9D6736C195F028B5293FE93159DF923DE7C7')
    r = router.contract.events.Deposit().processReceipt(receipt)
    print(r)


def get_eth_token_list():
    return StaticTokenList(StaticTokenList.DEFAULT_LISTS[Chains.ETH], Chains.web3_chain_id(Chains.ETH))


async def get_eth_token_info(contract_address, db, w3):
    token_list = TokenListCached(db, w3, get_eth_token_list())
    return await token_list.resolve_token(contract_address)


async def my_test_caching_token_list(db, w3):
    tl = TokenListCached(db, w3, get_eth_token_list())

    chi = await tl.resolve_token('0000494')

    # from the list!

    print(chi)
    assert chi.symbol == 'CHI' and chi.decimals == 0 and chi.chain_id == Chains.web3_chain_id(Chains.ETH) and \
           chi.address == '0x0000000000004946c0e9F43F4Dee607b0eF1fA1c'

    hegic = await tl.resolve_token('d411C')
    print(hegic)
    assert hegic.symbol == 'HEGIC' and hegic.decimals == 18 and \
           hegic.address == '0x584bC13c7D411c00c01A62e8019472dE68768430'

    wbtc = await tl.resolve_token('0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599')
    print(wbtc)
    assert wbtc.symbol == 'WBTC' and wbtc.decimals == 8 and wbtc.name == 'WrappedBTC'

    thor = await tl.resolve_token('5e8468044')
    print(thor)
    assert thor.symbol == 'THOR'

    # not in the list

    fold = await tl.resolve_token('0xd084944d3c05cd115c09d072b9f44ba3e0e45921')
    print(fold)
    assert fold and fold.symbol == 'FOLD' and fold.name == 'Manifold Finance'


async def demo_decoder(app: LpAppFramework):
    # await my_test_caching_token_list(app.deps.db, w3)

    aggr = AggregatorDataExtractor(app.deps)
    aggr_eth = aggr.get_by_chain(Chains.ETH)

    r = await aggr_eth.decode_swap_in('0xD45F100F3F48C786720167F5705B9D6736C195F028B5293FE93159DF923DE7C7')
    # swap in
    print(f'Swap In? {r}')

    r = await aggr_eth.decode_swap_out('0x926BC5212732BB863EE77D40A504BCA9583CF6D2F07090E2A3C468CFE6947357')
    # swap out
    print(f'Swap Out? {r}')

    aggr_avax = aggr.get_by_chain(Chains.AVAX)

    r = await aggr_avax.decode_swap_in('0xc2483005204f9b4d41d15024913807bc8d2a1714c55fae0b5f23b1d71d6affe3')
    # swap in
    print(f'Swap In? {r}')

    # todo:
    #  1) make Swap out using Avax => get tx id => test it here
    #  2) edit notificaiton text
    #  3) full debug pipeline => Midgard => Detector => Notifier => TG message test


class FilterTxMiddleware(WithDelegates, INotified):
    @staticmethod
    def is_ok_tx(tx: ThorTx):
        assets = (ETH_SYMBOL, AVAX_SYMBOL)
        if inp := tx.first_input_tx:
            if inp.first_asset in assets:
                return True
        if outp := tx.first_output_tx:
            if outp.first_asset in assets:
                return True
        return False

    async def on_data(self, sender, txs: List[ThorTx]):
        txs = [tx for tx in txs if self.is_ok_tx(tx)]
        await self.pass_data_to_listeners(txs, sender)


async def load_dex_txs(app: LpAppFramework):
    with open('../temp/dex.txt', 'r') as f:
        lines = f.readlines()
    tx_hashes = [line.split(' ')[0] for line in lines]

    d = app.deps

    fetcher_tx = TxFetcher(d)

    aggregator = AggregatorDataExtractor(d)
    fetcher_tx.add_subscriber(aggregator)

    # VVV

    vf = VolumeFillerUpdater(d)
    vf.update_pools_each_time = False
    await app.deps.price_pool_fetcher.reload_global_pools()
    aggregator.add_subscriber(vf)

    # VVV

    dex_analytics = DexAnalyticsCollector(d)
    vf.add_subscriber(dex_analytics)

    for tx_hash in tx_hashes:
        r = await fetcher_tx.fetch_one_batch(0, tx_hash)
        txs = fetcher_tx.merge_related_txs(r.txs)
        await fetcher_tx.pass_data_to_listeners(txs, fetcher_tx)


async def demo_find_aff(app: LpAppFramework):
    d = app.deps

    fetcher_tx = TxFetcher(d)
    dex_ex = AggregatorDataExtractor(d)
    vf = VolumeFillerUpdater(d)
    vf.update_pools_each_time = False
    await app.deps.price_pool_fetcher.reload_global_pools()

    dex_analytics = DexAnalyticsCollector(d)
    vf.add_subscriber(dex_analytics)

    print(os.getcwd())
    f = open('../temp/dex.txt', 'w')

    page = 0
    try:
        while True:
            batch = await fetcher_tx.fetch_one_batch(page)
            if batch:
                txs = fetcher_tx.merge_related_txs(batch.txs)
                await vf.on_data(None, txs)

                await dex_ex.on_data(None, txs)

                for tx in txs:
                    if tx.type == ThorTxType.TYPE_SWAP:
                        if tx.dex_aggregator_used:
                            print(tx.tx_hash, f' = {tx.full_rune:.1f} Rune; ', tx.dex_info, tx, file=f)
                            print(tx.tx_hash, tx.full_rune, 'Rune')
                            f.flush()

                            r = await dex_analytics.get_analytics()
                            print(r)

            page += 1
    finally:
        f.close()


async def demo_full_tx_pipeline(app: LpAppFramework):
    d = app.deps

    fetcher_tx = TxFetcher(d)

    aggregator = AggregatorDataExtractor(d)
    fetcher_tx.add_subscriber(aggregator)

    volume_filler = VolumeFillerUpdater(d)
    aggregator.add_subscriber(volume_filler)

    filter_middleware = FilterTxMiddleware()
    volume_filler.add_subscriber(filter_middleware)

    curve = DepthCurve.default()
    swap_notifier_tx = SwapTxNotifier(d, d.cfg.tx.swap, curve=curve)
    swap_notifier_tx.curve = None
    swap_notifier_tx.min_usd_total = 0.0
    filter_middleware.add_subscriber(swap_notifier_tx)

    swap_notifier_tx.add_subscriber(d.alert_presenter)

    # run the pipeline!
    # await fetcher_tx.run()
    #
    # txs = load_sample_txs('tests/sample_data/example_avax_swap_in.json')
    # await fetcher_tx.pass_data_to_listeners(txs, fetcher_tx)
    #
    # txs = load_sample_txs('tests/sample_data/example_eth_swap_out.json')
    # await fetcher_tx.pass_data_to_listeners(txs, fetcher_tx)

    # await demo_run_txs_example_file(fetcher_tx, 'example_swap_in_with_aff.json')

    # await asyncio.sleep(10)


async def demo_avax(app: LpAppFramework):
    w3 = Web3(Web3.HTTPProvider(f'https://api.avax.network/ext/bc/C/rpc'))
    print(w3.isConnected())

    tx = w3.eth.get_transaction('0xc2483005204f9b4d41d15024913807bc8d2a1714c55fae0b5f23b1d71d6affe3')
    print(tx)


async def show_dex_report(app: LpAppFramework):
    dex_analytics = DexAnalyticsCollector(app.deps)
    report = await dex_analytics.get_analytics(DAY * 30)
    print(report)
    sep()
    print(report.top_popular_assets())
    sep()
    print(report.top_popular_aggregators())
    report = report._replace(usd_per_rune=1.5)

    twitter_text = app.deps.loc_man[Language.ENGLISH_TWITTER].notification_text_dex_report(report)
    print(twitter_text)

    # await app.send_test_tg_message(txt=app.deps.loc_man.default.notification_text_dex_report(report))


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        # await demo_avax(app)
        # await demo_decoder(app)
        # await demo_full_tx_pipeline(app)
        # await demo_find_aff(app)
        # await load_dex_txs(app)
        await show_dex_report(app)


if __name__ == '__main__':
    asyncio.run(run())
