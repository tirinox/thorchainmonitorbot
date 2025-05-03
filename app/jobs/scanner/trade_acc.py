from typing import Iterable, Optional

from jobs.scanner.block_result import BlockResult
from jobs.scanner.tx import ThorTxMessage, ThorObservedTx
from lib.constants import thor_to_float
from lib.delegates import INotified, WithDelegates
from lib.logs import WithLogger
from models.asset import Asset
from models.memo import THORMemo, ActionType
from models.price import LastPriceHolder
from models.trade_acc import AlertTradeAccountAction


class TradeAccEventDecoder(WithLogger, INotified, WithDelegates):
    """
    This class is responsible for decoding deposits and withdrawals from the Trade Accounts.
    """

    def __init__(self, price_holder: LastPriceHolder):
        super().__init__()
        self.price_holder = price_holder

    async def on_data(self, sender, block: BlockResult):
        all_events = {}

        # Observed In transactions
        for observed_tx in block.all_observed_txs:
            if tr_dep_event := self._make_deposit(observed_tx, block.block_no):
                all_events[observed_tx.tx_id] = tr_dep_event

        # We need to check all transactions in the block for MsgDeposit and plain "sends" with memo
        for tx in block.txs:
            for message in tx.messages:
                if message.type == message.MsgDeposit or message.is_send:
                    # trade withdraw
                    tx_events = self._make_withdrawals(message, block.block_no, tx.tx_hash)
                    for event in tx_events:
                        all_events[event.tx_hash] = event

        # Unique for this block, but may not be unique across the entire blockchain
        unique_events = list(all_events.values())

        for event in unique_events:
            self.logger.info(f'TradeAccEvent: {event}')
            await self.pass_data_to_listeners(event)
        return unique_events

    def _make_deposit(self, obs_tx: ThorObservedTx, height) -> Optional[AlertTradeAccountAction]:
        if not obs_tx.is_inbound:
            return None

        memo = THORMemo.parse_memo(obs_tx.memo, no_raise=True)
        if not memo or memo.action != ActionType.TRADE_ACC_DEPOSIT:
            return None

        # here we override tx_id with inner tx id!
        tx_id = obs_tx.tx_id

        if len(obs_tx.coins) != 1:
            self.logger.warning(f'Tx {tx_id} has abnormal coins count: {len(obs_tx.coins)}')
            return None

        coin = obs_tx.coins[0]
        amount = thor_to_float(coin.amount)
        asset = Asset.from_string(coin.asset)
        asset_str = f'{asset.chain}~{asset.name}'
        usd_amount = self.price_holder.convert_to_usd(amount, asset_str)

        return AlertTradeAccountAction(
            tx_id,
            actor=obs_tx.from_address,
            destination_address=memo.dest_address,
            amount=amount,
            usd_amount=usd_amount,
            asset=asset_str,
            chain=asset.chain,
            is_deposit=True,
            height=height,
        )

    def _make_withdrawals(self, message: ThorTxMessage, height, tx_hash) -> Iterable[AlertTradeAccountAction]:
        memo = THORMemo.parse_memo(message.memo, no_raise=True)
        if not memo or memo.action != ActionType.TRADE_ACC_WITHDRAW:
            return

        for coin in message.coins:
            coin: dict
            amount = thor_to_float(coin['amount'])
            asset = Asset.from_string(coin['asset'])
            asset_str = f'{asset.chain}~{asset.name}'
            usd_amount = self.price_holder.convert_to_usd(amount, asset_str)
            actor = message.attrs['signer']

            yield AlertTradeAccountAction(
                tx_hash,
                actor=actor,
                destination_address=memo.dest_address,
                amount=amount,
                usd_amount=usd_amount,
                asset=asset_str,
                chain=asset.chain,
                is_deposit=False,
                height=height,
            )
