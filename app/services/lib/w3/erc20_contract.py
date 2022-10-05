from web3 import Web3

from services.lib.utils import load_json, async_wrap
from services.lib.w3.token_list import CONTRACT_DATA_BASE_PATH
from services.lib.w3.web3_helper import Web3Helper


class ERC20Contract:
    DEFAULT_ABI_ERC20 = f'{CONTRACT_DATA_BASE_PATH}/erc20.abi.json'

    def __init__(self, helper: Web3Helper, address):
        self.helper = Web3Helper
        self._contract = helper.w3.eth.contract(
            address=Web3.toChecksumAddress(address),
            abi=load_json(self.DEFAULT_ABI_ERC20)
        )

    @async_wrap
    def _get_token_info(self):
        name = self._contract.functions.name().call()
        symbol = self._contract.functions.symbol().call()
        decimals = self._contract.functions.decimals().call()
        return name, symbol, decimals

    async def get_token_info(self):
        # throws: BadFunctionCallOutput
        return await self._get_token_info()