from jobs.scanner.block_result import BlockResult
from lib.delegates import INotified, WithDelegates
from lib.logs import WithLogger


class CosmwasmExecuteDecoder(WithLogger, INotified, WithDelegates):
    def __init__(self, contract_whitelist):
        super().__init__()
        self.contract_whitelist = contract_whitelist

    def decode(self, data: BlockResult):
        for tx in data.txs:
            for message in tx.messages:
                if message.is_contract and message.contract_address in self.contract_whitelist:
                    yield tx

    async def on_data(self, sender, data: BlockResult):
        for tx in self.decode(data):
            await self.pass_data_to_listeners(tx)
