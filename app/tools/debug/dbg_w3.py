import asyncio

from web3 import Web3

from tools.lib.lp_common import LpAppFramework


async def get_abi(app: LpAppFramework, contract):
    api_key = app.deps.cfg.get('thor.circulating_supply.ether_scan_key')
    url = f'https://api.etherscan.io/api?module=contract&action=getabi&address={contract}&apikey={api_key}'
    print(url)
    async with app.deps.session.get(url) as reps:
        j = await reps.json()
        return j.get('result') if j.get('status') else None


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        key = app.deps.cfg.as_str('infura.key')
        w3 = Web3(Web3.HTTPProvider(f'https://mainnet.infura.io/v3/{key}'))
        # good = w3.isConnected()
        # print(f'{good = }')
        tx = w3.eth.get_transaction('0xD45F100F3F48C786720167F5705B9D6736C195F028B5293FE93159DF923DE7C7')
        print(Web3.toJSON(tx))

        dex_aggr = Web3.toChecksumAddress('0x0f2cd5df82959e00be7afeef8245900fc4414199')

        abi = await get_abi(app, dex_aggr)
        print(abi)

        contract = w3.eth.contract(address=dex_aggr, abi=abi)
        input = contract.decode_function_input(tx.input)
        print(input)

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
