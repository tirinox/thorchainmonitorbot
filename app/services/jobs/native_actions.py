from collections import Counter

from proto.thor_types import MsgSwap, MsgObservedTxIn, ObservedTx, MsgDeposit
from services.jobs.fetch.native_scan import BlockResult
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.memo import THORMemoParsed
from services.lib.utils import WithLogger


class NativeActionExtractor(WithDelegates, INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    def check_memo(self, tx):
        if tx.memo.count(':') >= 5:
            memo = THORMemoParsed.parse_memo(tx.memo)
            if memo and memo.dex_aggregator_address:
                self.logger.info(f'Swap memo: {tx.memo} => {memo}')
                print(tx)

    async def on_data(self, sender, block: BlockResult):

        for tx in block.txs:

            if len(tx.messages) > 1:
                print(f'{tx.hash} has {len(tx.messages)} messages')

            if isinstance(tx.first_message, MsgSwap):
                msg: MsgSwap = tx.first_message
                if msg.aggregator:
                    self.logger.info(f'Swap Aggr: {msg}')
                self.check_memo(msg.tx)
            elif isinstance(tx.first_message, MsgDeposit):
                self.check_memo(tx.first_message)

            elif isinstance(tx.first_message, MsgObservedTxIn):
                for subtx in tx.first_message.txs:
                    subtx: ObservedTx
                    if subtx.aggregator:
                        self.logger.info(f'Observed Tx Aggr: {subtx}')
                    self.check_memo(subtx.tx)
