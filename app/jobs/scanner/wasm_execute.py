from jobs.scanner.block_result import BlockResult
from lib.delegates import INotified, WithDelegates
from lib.logs import WithLogger


class CosmwasmExecuteDecoder(WithLogger, INotified, WithDelegates):
    def __init__(self, contract_whitelist=None):
        super().__init__()
        self.contract_whitelist = contract_whitelist

    def decode(self, block: BlockResult):
        for tx in block.txs:
            for message in tx.messages:
                if not message.is_contract:
                    continue
                if self.contract_whitelist and message.contract_address not in self.contract_whitelist:
                    continue
                yield tx

    async def on_data(self, sender, block: BlockResult):
        for tx in self.decode(block):
            await self.pass_data_to_listeners(tx)
