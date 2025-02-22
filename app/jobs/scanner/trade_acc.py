from typing import Iterable

from jobs.scanner.block_result import BlockResult
from jobs.scanner.tx import ThorTxMessage
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

    async def on_data(self, sender, data: BlockResult):
        all_events = {}
        for tx in data.txs:
            for message in tx.messages:
                if message.type == message.MsgObservedTxIn:
                    # trade deposit.
                    tx_events = self._make_deposits(message, data.block_no)
                elif message.type == message.MsgDeposit or message.is_send:
                    # trade withdraw
                    tx_events = self._make_withdrawals(message, data.block_no, tx.tx_hash)
                else:
                    tx_events = []

                for event in tx_events:
                    all_events[event.tx_hash] = event


        # Unique for this block, but may not be unique across the entire blockchain
        unique_events = list(all_events.values())

        for event in unique_events:
            self.logger.info(f'TradeAccEvent: {event}')
            await self.pass_data_to_listeners(event)
        return unique_events

    def _make_deposits(self, message: ThorTxMessage, height) -> Iterable[AlertTradeAccountAction]:
        for sub_tx in message.txs:
            in_tx: dict = sub_tx.get('tx', {})
            memo = THORMemo.parse_memo(in_tx.get('memo', ''), no_raise=True)

            if not memo or memo.action != ActionType.TRADE_ACC_DEPOSIT:
                continue

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
            actor = message['signer']

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
