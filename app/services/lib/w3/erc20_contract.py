from typing import Optional

from web3 import Web3
from web3._utils.events import EventLogErrorFlags

from services.lib.utils import load_json, async_wrap, str_to_bytes
from services.lib.w3.token_record import TokenRecord, CONTRACT_DATA_BASE_PATH
from services.lib.w3.web3_helper import Web3Helper


class ERC20Contract:
    DEFAULT_ABI_ERC20 = f'{CONTRACT_DATA_BASE_PATH}/erc20.abi.json'

    def __init__(self, helper: Web3Helper, address, chain_id):
        self.helper = Web3Helper
        self.address = address
        self.chain_id = chain_id
        self.contract = helper.w3.eth.contract(
            address=Web3.to_checksum_address(address),
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

    @staticmethod
    def restore_receipt_data(receipt_data: dict):
        if not receipt_data:
            return

        def restore(d, k):
            if not isinstance(d[k], bytes):
                d[k] = str_to_bytes(d[k])

        restore(receipt_data, 'blockHash')
        for log in receipt_data['logs']:
            restore(log, 'blockHash')
            topics = log['topics']
            for i in range(len(topics)):
                restore(topics, i)

    def get_transfer_events_from_receipt(self, receipt_data, filter_by_receiver=None):
        self.restore_receipt_data(receipt_data)

        transfers = self.contract.events.Transfer().process_receipt(receipt_data, EventLogErrorFlags.Discard)
        if filter_by_receiver:
            filter_by_receiver = str(filter_by_receiver).lower()
            transfers = [t for t in transfers if t['args']['to'].lower() == filter_by_receiver]
        return transfers
