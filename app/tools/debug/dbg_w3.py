import asyncio

from services.lib.w3.erc20_contract import ERC20Contract
from services.lib.w3.router_contract import TCRouterContract
from services.lib.w3.web3_helper import Web3Helper
from web3 import Web3

from tools.lib.lp_common import LpAppFramework


async def get_abi(app: LpAppFramework, contract):
    api_key = app.deps.cfg.get('thor.circulating_supply.ether_scan_key')
    url = f'https://api.etherscan.io/api?module=contract&action=getabi&address={contract}&apikey={api_key}'
    print(url)
    async with app.deps.session.get(url) as reps:
        j = await reps.json()
        return j.get('result') if j.get('status') else None


async def my_test_erc20(w3):
    token = ERC20Contract(w3, '0x584bc13c7d411c00c01a62e8019472de68768430')
    info = await token.get_token_info()
    print(info)


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        w3 = Web3Helper(app.deps.cfg)
        # swap in: '0xD45F100F3F48C786720167F5705B9D6736C195F028B5293FE93159DF923DE7C7'
        # tx = await w3.get_transaction_receipt('0xD45F100F3F48C786720167F5705B9D6736C195F028B5293FE93159DF923DE7C7')
        # tx = await w3.get_transaction('0x926BC5212732BB863EE77D40A504BCA9583CF6D2F07090E2A3C468CFE6947357')
        router = TCRouterContract(w3)
        r = router.contract.decode_function_input('0x00000000000000000000000000000000000000000000000029001122097e3444000000000000000000000000000000000000000000000000000000000000004000000000000000000000000000000000000000000000000000000000000000413d3a4254432e4254433a62633171363966796e636639783873706371637376747135656b37346a7973796535646a347a67366c383a32323631353235363a743a3000000000000000000000000000000000000000000000000000000000000000')

        print(r)

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
