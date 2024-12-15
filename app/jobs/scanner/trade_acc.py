from typing import List

from jobs.scanner.block_result import BlockResult
from jobs.scanner.tx import NativeThorTx
from lib.constants import thor_to_float
from lib.delegates import INotified, WithDelegates
from lib.logs import WithLogger
from models.asset import Asset
from models.memo import THORMemo, ActionType, is_action
from models.price import LastPriceHolder
from models.trade_acc import AlertTradeAccountAction
# from proto fixme


class TradeAccEventDecoder(WithLogger, INotified, WithDelegates):
    """
    This class is responsible for decoding deposits and withdrawals from the Trade Accounts.
    """

    def __init__(self, price_holder: LastPriceHolder):
        super().__init__()
        self.price_holder = price_holder

    async def on_data(self, sender, data: BlockResult):
        all_events = {}
        for tx in data.txs:
            if deep_memo := tx.deep_memo:
                if memo := THORMemo.parse_memo(deep_memo, no_raise=True):
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

    def _make_deposit(self, memo, tx: NativeThorTx) -> List[AlertTradeAccountAction]:
        observed_in_tx = tx.first_message

        for sub_tx in observed_in_tx.txs:
            in_tx: dict = sub_tx['tx']

            # here we override tx_id with inner tx id!
            tx_id = in_tx['id']
            coins = in_tx['coins']

            if len(coins) != 1:
                self.logger.warning(f'Tx {tx_id} has abnormal coins count: {len(coins)}')
                continue

            coin = coins[0]
            amount = thor_to_float(coin['amount'])
            asset = Asset.from_string(coin['asset'])
            asset_str = f'{asset.chain}~{asset.name}'
            usd_amount = self.price_holder.convert_to_usd(amount, asset_str)

            yield AlertTradeAccountAction(
                tx_id,
                actor=in_tx['from_address'],
                destination_address=memo.dest_address,
                amount=amount,
                usd_amount=usd_amount,
                asset=asset_str,
                chain=asset.chain,
                is_deposit=True,
            )

    def _make_withdraw(self, memo, tx: NativeThorTx) -> List[AlertTradeAccountAction]:
        msg = tx.first_message
        for coin in msg.coins:
            coin: dict
            amount = thor_to_float(coin['amount'])
            asset = Asset.from_string(coin['asset'])
            asset_str = f'{asset.chain}~{asset.name}'
            usd_amount = self.price_holder.convert_to_usd(amount, asset_str)
            actor = msg['signer']

            yield AlertTradeAccountAction(
                tx.tx_hash,
                actor=actor,
                destination_address=memo.dest_address,
                amount=amount,
                usd_amount=usd_amount,
                asset=asset_str,
                chain=asset.chain,
                is_deposit=False,
            )
