from typing import List

from api.aionode.types import thor_to_float
from jobs.scanner.block_loader import BlockResult, parse_thor_address
from lib.db import DB
from lib.delegates import INotified, WithDelegates
from lib.logs import WithLogger
from models.memo import THORMemo, ActionType, is_action
from models.price import LastPriceHolder
from models.runepool import AlertRunePoolAction
from proto.access import NativeThorTx
from proto.common import Asset
from proto.types import MsgDeposit


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
            if tx.memo:
                if memo := THORMemo.parse_memo(tx.memo, no_raise=True):
                    if is_action(memo.action, (ActionType.RUNEPOOL_ADD, ActionType.RUNEPOOL_WITHDRAW)):
                        tx_events = self._convert_tx_to_event(tx, memo, data.block_no)
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

        if not isinstance(tx.first_message, MsgDeposit):
            self.logger.error(f'Unexpected message type in RUNE pool tx: {tx.first_message}')
            return results

        usd_per_rune = self.price_holder.usd_per_rune

        for coin in tx.first_message.coins:
            if coin.asset != Asset('THOR', 'RUNE', 'RUNE'):
                self.logger.error(f'Unexpected asset in RUNE pool tx: {coin.asset}')
                continue

            actor = parse_thor_address(tx.first_message.signer)
            amount = thor_to_float(coin.amount)
            dest_address = memo.dest_address or actor
            results.append(AlertRunePoolAction(
                tx.hash,
                actor,
                destination_address=dest_address,
                amount=amount,
                usd_amount=usd_per_rune * amount,
                is_deposit=memo.action == ActionType.RUNEPOOL_ADD,
                height=height,
                memo=memo,
            ))

        return results
