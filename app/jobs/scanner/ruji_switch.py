from jobs.scanner.block_result import BlockResult
from lib.db import DB
from lib.delegates import INotified, WithDelegates
from lib.logs import WithLogger
from models.memo import THORMemo, ActionType, is_action
from models.price import LastPriceHolder
from models.ruji import EventRujiSwitch


class RujiSwitchEventDecoder(WithLogger, INotified, WithDelegates):
    def __init__(self, db: DB, price_holder: LastPriceHolder):
        super().__init__()
        self.redis = db.redis
        self.price_holder = price_holder

    async def on_data(self, sender, data: BlockResult):
        switch_txs = []
        for observed_tx_in in data.all_observed_tx_in:
            if memo_str := observed_tx_in.memo:
                if memo_ob := THORMemo.parse_memo(memo_str, no_raise=True):
                    if is_action(memo_ob.action, ActionType.SWITCH):
                        switch_txs.append(EventRujiSwitch(observed_tx_in))

        for sw in switch_txs:
            # EventRujiSwitch
            await self.pass_data_to_listeners(sw)


class CosmwasmExecuteDecoder(WithLogger, INotified, WithDelegates):
    def __init__(self, db: DB, contract_whitelist):
        super().__init__()
        self.redis = db.redis
        self.contract_whitelist = contract_whitelist

    async def on_data(self, sender, data: BlockResult):
        for tx in data.txs:
            for message in tx.messages:
                if message.is_contract and message.contract_address in self.contract_whitelist:
                    await self.pass_data_to_listeners(message)
