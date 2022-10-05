import asyncio

from services.lib.w3.aggr_contract import AggregatorContract
from services.lib.w3.erc20_contract import ERC20Contract
from services.lib.w3.router_contract import TCRouterContract
from services.lib.w3.token_list import TokenListCached, StaticTokenList
from services.lib.w3.token_record import ETH_CHAIN_ID
from services.lib.w3.web3_helper import Web3Helper
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


async def demo_decode_swap_in(w3, tx_hash):
    tx = await w3.get_transaction(tx_hash)
    aggr = AggregatorContract(w3)
    swap_in_call = aggr.decode_input(tx.input)
    print('----- swap in ------')
    print(swap_in_call)

    token = ERC20Contract(w3, swap_in_call.from_token, ETH_CHAIN_ID)
    token_info = await token.get_token_info()

    print(f'{token_info = }')

    # now the current task is to make a class that aggregates token list and cached token info from the block chain!


async def my_test_caching_token_list(db, w3):
    static_list = StaticTokenList(StaticTokenList.DEFAULT_TOKEN_LIST_ETH_PATH, ETH_CHAIN_ID)
    tl = TokenListCached(db, w3, static_list)

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

    # not in the list

    fold = await tl.resolve_token('0xd084944d3c05cd115c09d072b9f44ba3e0e45921')
    print(fold)
    assert fold and fold.symbol == 'FOLD' and fold.name == 'Manifold Finance'


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        w3 = Web3Helper(app.deps.cfg)

        await my_test_caching_token_list(app.deps.db, w3)

        # await demo_process_events(w3)
        # await demo_decode_swap_in(w3, '0xD45F100F3F48C786720167F5705B9D6736C195F028B5293FE93159DF923DE7C7')

        # swap in: '0xD45F100F3F48C786720167F5705B9D6736C195F028B5293FE93159DF923DE7C7'
        # tx = await w3.get_transaction('0x926BC5212732BB863EE77D40A504BCA9583CF6D2F07090E2A3C468CFE6947357')
        # print(Web3.toJSON(tx))
        # await my_test_erc20(w3)
        # dex_aggr = Web3.toChecksumAddress('0x0f2cd5df82959e00be7afeef8245900fc4414199')
        # abi = await get_abi(app, dex_aggr)
        # print(abi)

        # contract = w3.eth.contract(address=dex_aggr, abi=abi)
        # input = contract.decode_function_input(tx.input)
        # print(input)

        """
        SwapIN detection!
        1. aggr list => config
        2. load aggr ABI and cache it!
        3. decode tx input => detect swap in
        
        SwapOut detection!
        1. Midgard -> actions -> swap -> meta -> memo -> parse
        2. load dest_token from Infura/local token list
        3.
        """


if __name__ == '__main__':
    asyncio.run(run())
