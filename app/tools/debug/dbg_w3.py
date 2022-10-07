import asyncio

from services.lib.constants import Chains
from services.lib.texts import sep
from services.lib.w3.aggregator import AggregatorDataExtractor
from services.lib.w3.erc20_contract import ERC20Contract
from services.lib.w3.router_contract import TCRouterContract
from services.lib.w3.token_list import TokenListCached, StaticTokenList
from services.lib.w3.token_record import ETH_CHAIN_ID
from services.lib.w3.web3_helper import Web3HelperCached
from tools.lib.lp_common import LpAppFramework


async def get_abi(app: LpAppFramework, contract):
    api_key = app.deps.cfg.get('thor.circulating_supply.ether_scan_key')
    url = f'https://api.etherscan.io/api?module=contract&action=getabi&address={contract}&apikey={api_key}'
    print(url)
    async with app.deps.session.get(url) as reps:
        j = await reps.json()
        return j.get('result') if j.get('status') else None


async def my_test_erc20(w3):
    token = ERC20Contract(w3, '0x584bc13c7d411c00c01a62e8019472de68768430', chain_id=ETH_CHAIN_ID)
    info = await token.get_token_info()
    print(info)


async def demo_process_events(w3):
    router = TCRouterContract(w3)

    # how to process events:
    receipt = await w3.get_transaction_receipt('0xD45F100F3F48C786720167F5705B9D6736C195F028B5293FE93159DF923DE7C7')
    r = router.contract.events.Deposit().processReceipt(receipt)
    print(r)


async def demo_decode_swap_in(deps, tx_hash):
    aggr = AggregatorDataExtractor(deps)

    amt = await aggr.decode_swap_in(tx_hash, Chains.ETH)
    print(f'Swap IN: {amt}')


def get_eth_token_list():
    return StaticTokenList(StaticTokenList.DEFAULT_TOKEN_LIST_ETH_PATH, ETH_CHAIN_ID)


async def get_eth_token_info(contract_address, db, w3):
    token_list = TokenListCached(db, w3, get_eth_token_list())
    return await token_list.resolve_token(contract_address)


async def demo_decode_swap_out(deps, tx_hash):
    aggr = AggregatorDataExtractor(deps)
    amt = await aggr.decode_swap_out(tx_hash, Chains.ETH)

    print(f'Swap OUT: {amt}')


async def my_test_caching_token_list(db, w3):
    tl = TokenListCached(db, w3, get_eth_token_list())

    chi = await tl.resolve_token('0000494')

    # from the list!

    print(chi)
    assert chi.symbol == 'CHI' and chi.decimals == 0 and chi.chain_id == ETH_CHAIN_ID and \
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


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        w3 = Web3HelperCached(app.deps.cfg, app.deps.db)

        await my_test_caching_token_list(app.deps.db, w3)

        # await demo_process_events(w3)
        sep()
        await demo_decode_swap_in(app.deps, '0xD45F100F3F48C786720167F5705B9D6736C195F028B5293FE93159DF923DE7C7')
        sep()
        await demo_decode_swap_out(app.deps, '0x926BC5212732BB863EE77D40A504BCA9583CF6D2F07090E2A3C468CFE6947357')

        """
        SwapIN detection!
        1. aggr list => config
        2. load aggr ABI and cache it!
        3. decode tx input => detect swap in
        
        SwapOut detection!
        1. Midgard -> actions -> swap -> meta -> memo -> parse
        2. load dest_token from Infura/local token list
        3.
        
        Now. Given a Tx Id
        
        
        """


if __name__ == '__main__':
    asyncio.run(run())
