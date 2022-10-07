from typing import Optional

from web3 import Web3
from web3._utils.events import EventLogErrorFlags

from services.lib.utils import load_json, async_wrap
from services.lib.w3.token_record import TokenRecord, CONTRACT_DATA_BASE_PATH
from services.lib.w3.web3_helper import Web3Helper


class ERC20Contract:
    DEFAULT_ABI_ERC20 = f'{CONTRACT_DATA_BASE_PATH}/erc20.abi.json'

    def __init__(self, helper: Web3Helper, address, chain_id):
        self.helper = Web3Helper
        self.address = address
        self.chain_id = chain_id
        self.contract = helper.w3.eth.contract(
            address=Web3.toChecksumAddress(address),
            abi=load_json(self.DEFAULT_ABI_ERC20)
        )

    @async_wrap
    def _get_token_info(self):
        name = self.contract.functions.name().call()
        symbol = self.contract.functions.symbol().call()
        decimals = self.contract.functions.decimals().call()
        return TokenRecord(
            self.address,
            self.chain_id,
            decimals, name, symbol, ''
        )

    async def get_token_info(self) -> Optional[TokenRecord]:
        # throws: BadFunctionCallOutput
        return await self._get_token_info()

    def get_transfer_events_from_receipt(self, receipt_data, filter_by_receiver=None):
        # fixme: it needs HexBytes inside the logs, bot str
        """
        AttributeDict({
            'address': '0xa5f2211B9b8170F694421f2046281775E8468044',
  -->          'blockHash': HexBytes('0x9b3dff70b45533efc147bded4d397cbe0acedcdafdf4b700892d76417ec69b24'),
            'blockNumber': 15440224,
            'data': '0x0000000000000000000000000000000000000000000003c5ba751b73fe6d3203',
            'logIndex': 36,
            'removed': False,
            'topics': [
  -->          HexBytes('0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'),
  -->          HexBytes('0x0000000000000000000000003d3f13f2529ec3c84b2940155effbf9b39a8f3ec'),
  -->          HexBytes('0x0000000000000000000000001e240f76bcf08219e70b2c3c20f20f5ec4b43585')],
  -->          'transactionHash': HexBytes('0x926bc5212732bb863ee77d40a504bca9583cf6d2f07090e2a3c468cfe6947357'),
            'transactionIndex': 12})
        """

        transfers = self.contract.events.Transfer().processReceipt(receipt_data, EventLogErrorFlags.Discard)
        if filter_by_receiver:
            filter_by_receiver = str(filter_by_receiver).lower()
            transfers = [t for t in transfers if t['args']['to'].lower() == filter_by_receiver]
        return transfers
