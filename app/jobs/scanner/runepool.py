from typing import List

from api.aionode.types import thor_to_float
from jobs.scanner.block_result import BlockResult
from jobs.scanner.tx import NativeThorTx
from lib.db import DB
from lib.delegates import INotified, WithDelegates
from lib.logs import WithLogger
from models.asset import is_rune
from models.memo import THORMemo, ActionType, is_action
from models.price import LastPriceHolder
from models.runepool import AlertRunePoolAction


class RunePoolEventDecoder(WithLogger, INotified, WithDelegates):
    """
    This class is responsible for decoding deposits and withdrawals from RUNEPool.
    """

    def __init__(self, db: DB, price_holder: LastPriceHolder):
        super().__init__()
        self.redis = db.redis
        self.price_holder = price_holder

    async def on_data(self, sender, data: BlockResult):
        all_events = {}
        for tx in data.txs:
            if memo_str := tx.deep_memo:
                if memo_ob := THORMemo.parse_memo(memo_str, no_raise=True):
                    if is_action(memo_ob.action, (ActionType.RUNEPOOL_ADD, ActionType.RUNEPOOL_WITHDRAW)):
                        tx_events = self._convert_tx_to_event(tx, memo_ob, data.block_no)
                        for event in tx_events:
                            all_events[event.tx_hash] = event

        # Unique for this block, but may not be unique across the entire blockchain
        unique_events = list(all_events.values())

        for event in unique_events:
            self.logger.info(f'Rune pool events: {event}')
            await self.pass_data_to_listeners(event)

        return unique_events

    def _convert_tx_to_event(self, tx: NativeThorTx, memo: THORMemo, height) -> List[AlertRunePoolAction]:
        results = []
        if not tx or not tx.first_message:
            self.logger.error(f'Empty tx or message in RUNE pool tx: {tx}')
            return results

        if tx.first_message.type != tx.first_message.MsgDeposit:
            self.logger.error(f'Unexpected message type in RUNE pool tx: {tx.first_message}')
            return results

        usd_per_rune = self.price_holder.usd_per_rune

        for coin in tx.first_message.coins:
            if not is_rune(asset := coin['asset']):
                self.logger.error(f'Unexpected asset in RUNE pool tx: {asset}')
                continue

            actor = tx.first_message['signer']

            if memo.action == ActionType.RUNEPOOL_WITHDRAW:
                withdraw_event = next(
                    (e for e in tx.events if e.type == 'rune_pool_withdraw'),
                    None
                )
                amount = withdraw_event.get('rune_amount')
            else:
                amount = coin.get('amount')

            if not amount:
                self.logger.error(f'No amount in RUNE pool tx: {tx}')
                continue

            amount = thor_to_float(amount)

            dest_address = memo.dest_address or actor
            results.append(AlertRunePoolAction(
                tx.tx_hash,
                actor,
                destination_address=dest_address,
                amount=amount,
                usd_amount=usd_per_rune * amount,
                is_deposit=memo.action == ActionType.RUNEPOOL_ADD,
                height=height,
                memo=memo,
            ))

        return results
