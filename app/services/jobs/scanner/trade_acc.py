from typing import List

from proto.access import NativeThorTx, parse_thor_address
from proto.common import Tx
from services.jobs.scanner.block_loader import BlockResult
from services.lib.constants import thor_to_float
from services.lib.db import DB
from services.lib.delegates import INotified, WithDelegates
from services.lib.logs import WithLogger
from services.models.memo import THORMemo, ActionType, is_action
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
        all_events = {}
        for tx in data.txs:
            if tx.memo:
                if memo := THORMemo.parse_memo(tx.memo, no_raise=True):
                    if is_action(memo.action, (ActionType.TRADE_ACC_WITHDRAW, ActionType.TRADE_ACC_DEPOSIT)):
                        tx_events = self._convert_tx_to_event(tx, memo)
                        for event in tx_events:
                            all_events[event.tx_hash] = event

        # Unique for this block, but may not be unique across the entire blockchain
        unique_events = list(all_events.values())

        for event in unique_events:
            self.logger.info(f'TradeAccEvent: {event}')
            await self.pass_data_to_listeners(event)
        return unique_events

    def _convert_tx_to_event(self, tx: NativeThorTx, memo: THORMemo) -> List[AlertTradeAccountAction]:
        results = []

        if not tx:
            self.logger.warning('No tx in the event')
            return results

        if len(tx.messages) != 1:
            self.logger.warning(f'Tx has abnormal messages count: {len(tx.messages)}')
            return results

        if memo.action == ActionType.TRADE_ACC_WITHDRAW:
            results += list(self._make_withdraw(memo, tx))

        elif memo.action == ActionType.TRADE_ACC_DEPOSIT:
            results += list(self._make_deposit(memo, tx))

        return results

    def _make_deposit(self, memo, tx) -> List[AlertTradeAccountAction]:
        observed_in_tx = tx.first_message

        for sub_tx in observed_in_tx.txs:
            in_tx: Tx = sub_tx.tx

            # here we override tx_id with inner tx id!
            tx_id = in_tx.id

            if len(in_tx.coins) != 1:
                self.logger.warning(f'Tx {tx_id} has abnormal coins count: {len(in_tx.coins)}')
                continue

            coin = in_tx.coins[0]
            amount = thor_to_float(coin.amount)
            asset = f'{coin.asset.chain}~{coin.asset.symbol}'
            usd_amount = self.price_holder.convert_to_usd(amount, asset)

            yield AlertTradeAccountAction(
                tx_id,
                actor=in_tx.from_address,
                destination_address=memo.dest_address,
                amount=amount,
                usd_amount=usd_amount,
                asset=asset,
                chain=coin.asset.chain,
                is_deposit=True,
            )

    def _make_withdraw(self, memo, tx) -> List[AlertTradeAccountAction]:
        coins = tx.first_message.coins
        for coin in coins:
            amount = thor_to_float(coin.amount)
            asset = f'{coin.asset.chain}~{coin.asset.symbol}'
            usd_amount = self.price_holder.convert_to_usd(amount, asset)
            actor = parse_thor_address(tx.first_message.signer)

            yield AlertTradeAccountAction(
                tx.hash,
                actor=actor,
                destination_address=memo.dest_address,
                amount=amount,
                usd_amount=usd_amount,
                asset=asset,
                chain=coin.asset.chain,
                is_deposit=False,
            )
