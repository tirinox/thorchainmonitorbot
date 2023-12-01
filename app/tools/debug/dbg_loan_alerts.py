import asyncio

from services.jobs.achievement.extractor import AchievementsExtractor
from services.jobs.fetch.borrowers import BorrowersFetcher
from services.jobs.scanner.event_db import EventDatabase
from services.jobs.scanner.loan_extractor import LoanExtractorBlock
from services.jobs.scanner.native_scan import NativeScannerBlock
from services.lib.money import DepthCurve
from services.lib.texts import sep
from services.notify.types.loans_notify import LoanTxNotifier
from tools.lib.lp_common import LpAppFramework


async def debug_block_analyse(app: LpAppFramework, block_no):
    scanner = NativeScannerBlock(app.deps)
    # await scanner.run()
    blk = await scanner.fetch_one_block(block_no)
    print(blk)
    sep()

    # loan (ETH => ETH.USDC)
    # DecodedEvent(type='burn', attributes={'burner': 'thor1v8ppstuf6e3x0r4glqc68d5jqcs2tf38cg2q6y', 'amount': 36503690000, 'asset': 'TOR'}, height=12258889)
    # DecodedEvent(type='loan_open', attributes={'collateral_deposited': '49990976', 'debt_issued': '36503690000', 'collateralization_ratio': '22722', 'collateral_asset': 'ETH.ETH', 'target_asset': 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48', 'owner': '0x08d2c744fd60f2dca8c1885d3aa03ff6d3fa5d11'}, height=12258889)
    # Tx(body=TxBody(messages=[MsgObservedTxIn(txs=[ObservedTx(tx=Tx(id='A313D2BD6B573B39C90A7E2E7EE691A30A56E4D14DE9140EBD88215C10277336', chain='ETH', from_address='0x08d2c744fd60f2dca8c1885d3aa03ff6d3fa5d11', to_address='0xB4C6501c98C2643A73f6E31c600Ec7d3B9ec4e87', coins=[Coin(asset=Asset(chain='ETH', symbol='ETH', ticker='ETH'), amount='50000000')], gas=[Coin(asset=Asset(chain='ETH', symbol='ETH', ticker='ETH'), amount='90840')], memo='$+:ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48:0x08d2c744Fd60F2dca8C1885D3AA03Ff6D3fA5d11:32795346454:t:0'), status=0, out_hashes=[], block_height=17968413, signers=[], observed_pub_key='thorpub1addwnpepqgau85fvv7n3dpzvxu2fu4lz7n4mt8kqjcds32kwngs0lpmhmu86guq0drw', keysign_ms=0, finalise_height=17968413, aggregator='', aggregator_target='', aggregator_target_limit='')], signer=b"'l\xf1SY\xfd\xf0\x90;\xc6\x9f\x9d-\x86\xb1\x9bg3!8")]), auth_info=AuthInfo(signer_infos=[SignerInfo(public_key=Any(type_url='/cosmos.crypto.secp256k1.PubKey', value=b'\n!\x03ETH\x18\xae\x7f\x0c\xb5\xebW\xea\x14\xb0\xc2\xd2]\xca\xaa\xb9N\x8f\x80\xe1\xe3\x10,\xbc\xa9\xe7\xd0\x83\x98'), mode_info=ModeInfo(single=ModeInfoSingle(mode=1)), sequence=862433)], fee=Fee(gas_limit=4000000000)), signatures=[b'\x08V\xcc\x17@\x1a\x15\x0bj\x05\xff/}J\xe6\x841\xc7\xf1\xb1\x8c\xaf\x9a\xbf\x92,o\x065"2E(\x88I\x02\xcf\xc3\x86\x1cC\x03\xf1t\xb1\x9eM\x9aI\x01\x9c\xe9T\x82\x15ssI\x1d\x0e\xdb=\xf6\x95'])

    # ----

    # loan (ETH => RUNE)
    # DecodedEvent(type='loan_open', attributes={'collateral_deposited': '39994234', 'debt_issued': '28818980000', 'collateralization_ratio': '22946', 'collateral_asset': 'ETH.ETH', 'target_asset': 'THOR.RUNE', 'owner': '0xf1da1837154d027f244dc86dd8cb0fefee3e2ce0'}, height=12262380)
    # Tx(body=TxBody(messages=[MsgObservedTxIn(txs=[ObservedTx(tx=Tx(id='46C91800C655212DBBC92B3865C4FA6230AB034AB43E1FEAF45787229162B55A', chain='ETH', from_address='0xf1da1837154d027f244dc86dd8cb0fefee3e2ce0', to_address='0x8629B0b0775BF3405A7e4d173E92C7c6258eB981', coins=[Coin(asset=Asset(chain='ETH', symbol='ETH', ticker='ETH'), amount='40000000')], gas=[Coin(asset=Asset(chain='ETH', symbol='ETH', ticker='ETH'), amount='100008')], memo='$+:THOR.RUNE:thor17alnfupgv5yd76rjaysjn5a2skp6t93dk7pjxv:17028217401:t:0'), status=0, out_hashes=[], block_height=17970150, signers=[], observed_pub_key='thorpub1addwnpepq0e6wzgrlg4rdrm6kwlnv6nhfx3rmtsjyc2p3q6j43ncp9zlsxemj3jm23l', keysign_ms=0, finalise_height=17970150, aggregator='', aggregator_target='', aggregator_target_limit='')], signer=b'T\x87rk`2\xd2\x9dq`\xad\xad\xd6-\x9b\x00\xaa\x03,K')]), auth_info=AuthInfo(signer_infos=[SignerInfo(public_key=Any(type_url='/cosmos.crypto.secp256k1.PubKey', value=b'\n!\x03\x91t$\\\x88\xac\xff\x1b\n\xf6\x02N\xc7n\xfd*\xee\xab\x08\xb2\r)\x06\x06\xb0m\xfd2,\xea\x9bY'), mode_info=ModeInfo(single=ModeInfoSingle(mode=1)), sequence=296266)], fee=Fee(gas_limit=4000000000)), signatures=[b'\x04\xf0\xc1\x10XHm\xe2\xcf\x18Mt-$\xef\x89\xdc\x1a\x8c\x17nR\xb95\xc7DE\x06\xf5\x1b7\xd6e\xc2?~\x84}\x8cb\xa4\xf7\xa7\xfe\x8d\x1b\xbf\xbdB\xf0*"\xe2~\xe2\x9d\xf6US\xda\x8e\xabw\xce'])

    # naex = SwapExtractorBlock(app.deps)
    # actions = await naex.on_data(None, blk)
    # print(actions)


async def debug_full_pipeline(app, start=None, tx_id=None, single_block=False):
    d = app.deps

    # Block scanner: the source of the river
    d.block_scanner = NativeScannerBlock(d, last_block=start)
    d.block_scanner.one_block_per_run = single_block
    d.block_scanner.allow_jumps = False

    # Swap notifier (when it finishes)
    curve_pts = d.cfg.get_pure('tx.curve', default=DepthCurve.DEFAULT_TX_VS_DEPTH_CURVE)
    curve = DepthCurve(curve_pts)

    loan_extractor = LoanExtractorBlock(d)
    d.block_scanner.add_subscriber(loan_extractor)

    loan_notifier = LoanTxNotifier(d, curve=curve)
    loan_extractor.add_subscriber(loan_notifier)
    loan_notifier.add_subscriber(d.alert_presenter)
    await loan_notifier._ev_db.clear_tx_started_cache()

    # Run all together
    if single_block:
        await d.block_scanner.run_once()
    else:
        while True:
            await d.block_scanner.run()
            await asyncio.sleep(5.9)


async def debug_tx_records(app: LpAppFramework, tx_id):
    ev_db = EventDatabase(app.deps.db)

    props = await ev_db.read_tx_status(tx_id)
    sep('swap')
    print(props)

    sep('tx')
    tx = props.build_tx(app.deps.price_holder)
    print(tx)


async def demo_lending_stats(app: LpAppFramework):
    borrowers_fetcher = BorrowersFetcher(app.deps)
    r = await borrowers_fetcher.fetch()
    print(r)
    sep()
    events = await AchievementsExtractor(app.deps).extract_events_by_type(None, r)
    print(events)


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        await app.deps.pool_fetcher.reload_global_pools()
        await app.deps.last_block_fetcher.run_once()

        await demo_lending_stats(app)

        # await debug_block_analyse(app, 12262380)
        # await debug_tx_records(app, 'xxx')
        # await debug_full_pipeline(
        #     app,
        #     start=12258889,
        #     # tx_id='xx',
        #     # single_block=True
        # )


if __name__ == '__main__':
    asyncio.run(run())
