from typing import Optional

from proto.access import NativeThorTx, parse_thor_address
from proto.common import Tx
from services.jobs.scanner.block_loader import BlockResult
from services.lib.constants import thor_to_float
from services.lib.db import DB
from services.lib.delegates import INotified, WithDelegates
from services.lib.logs import WithLogger
from services.models.memo import THORMemo, ActionType
from services.models.price import LastPriceHolder
from services.models.trade_acc import AlertTradeAccountAction


class TradeAccEventDecoder(WithLogger, INotified, WithDelegates):
    """
    This class is responsible for decoding deposits and withdrawals from the Trade Accounts.
    """

    def __init__(self, db: DB, price_holder: LastPriceHolder):
        super().__init__()
        self.redis = db.redis
        self.price_holder = price_holder

    async def on_data(self, sender, data: BlockResult):
        events = {}
        for tx in data.txs:
            if memo := THORMemo.parse_memo(tx.memo):
                if memo.action in (ActionType.TRADE_ACC_WITHDRAW, ActionType.TRADE_ACC_DEPOSIT):
                    event = self._convert_tx_to_event(tx, memo)
                    events[event.tx_hash] = event

        unique_events = list(events.values())

        for event in unique_events:
            await self.pass_data_to_listeners(event)
        return unique_events

    def _convert_tx_to_event(self, tx: NativeThorTx, memo: THORMemo) -> Optional[AlertTradeAccountAction]:
        if not tx:
            self.logger.warning('No tx in the event')
            return

        if len(tx.messages) != 1:
            self.logger.warning(f'Tx has abnormal messages count: {len(tx.messages)}')
            return

        if memo.action == ActionType.TRADE_ACC_WITHDRAW:
            return self._make_withdraw(memo, tx)

        elif memo.action == ActionType.TRADE_ACC_DEPOSIT:
            return self._make_deposit(memo, tx)

    def _make_deposit(self, memo, tx):
        tx_id = tx.hash
        observed_in_tx = tx.first_message
        if len(observed_in_tx.txs) != 1:
            self.logger.warning(f'ObservedTxIn {tx_id} has abnormal txs count: {len(observed_in_tx.txs)}')
            return
        in_tx: Tx = observed_in_tx.txs[0].tx

        # here we override tx_id with inner tx id!
        tx_id = in_tx.id

        if len(in_tx.coins) != 1:
            self.logger.warning(f'Tx {tx_id} has abnormal coins count: {len(in_tx.coins)}')
            return
        coin = in_tx.coins[0]
        amount = thor_to_float(coin.amount)
        asset = f'{coin.asset.chain}~{coin.asset.symbol}'
        usd_amount = self.price_holder.convert_to_usd(amount, asset)

        return AlertTradeAccountAction(
            tx_id,
            actor=in_tx.from_address,
            destination_address=memo.dest_address,
            amount=amount,
            usd_amount=usd_amount,
            asset=asset,
            chain=coin.asset.chain,
            is_deposit=True,
        )

    def _make_withdraw(self, memo, tx):
        coins = tx.first_message.coins
        if len(coins) != 1:
            self.logger.warning(f'Tx {tx.hash} has abnormal coins count: {len(coins)}')
            return
        coin = coins[0]
        amount = thor_to_float(coin.amount)
        asset = f'{coin.asset.chain}~{coin.asset.symbol}'
        usd_amount = self.price_holder.convert_to_usd(amount, asset)
        actor = parse_thor_address(tx.first_message.signer)

        return AlertTradeAccountAction(
            tx.hash,
            actor=actor,
            destination_address=memo.dest_address,
            amount=amount,
            usd_amount=usd_amount,
            asset=asset,
            chain=coin.asset.chain,
            is_deposit=False,
        )
