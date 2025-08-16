from typing import List

from api.aionode.types import thor_to_float
from jobs.fetch.cached.pool import PoolCache
from jobs.scanner.block_result import BlockResult
from jobs.scanner.tx import ThorTxMessage
from lib.db import DB
from lib.delegates import INotified, WithDelegates
from lib.logs import WithLogger
from models.asset import is_rune
from models.memo import THORMemo, ActionType, is_action
from models.runepool import AlertRunePoolAction


class RunePoolEventDecoder(WithLogger, INotified, WithDelegates):
    """
    This class is responsible for decoding deposits and withdrawals from RUNEPool.
    """

    def __init__(self, db: DB, pool_cache: PoolCache):
        super().__init__()
        self.redis = db.redis
        self.pool_cache = pool_cache

    async def on_data(self, sender, data: BlockResult):
        usd_per_rune = await self.pool_cache.get_usd_per_rune()

        all_events = {}
        for tx in data.txs:
            # RunePool Deposit/Withdraw are MsgDeposit With top-layer Memo: "POOL+/POOL-"
            if memo_str := tx.memo:
                if memo_ob := THORMemo.parse_memo(memo_str, no_raise=True):
                    if is_action(memo_ob.action, (ActionType.RUNEPOOL_ADD, ActionType.RUNEPOOL_WITHDRAW)):
                        for message in tx.messages:
                            tx_events = self._convert_tx_to_event(tx, message, memo_ob, data.block_no, usd_per_rune)
                            for event in tx_events:
                                all_events[event.tx_hash] = event

        # Unique for this block, but may not be unique across the entire blockchain
        unique_events = list(all_events.values())

        for event in unique_events:
            self.logger.info(f'Rune pool events: {event}')
            await self.pass_data_to_listeners(event)

        return unique_events

    def _convert_tx_to_event(self, tx, message: ThorTxMessage, memo: THORMemo, height, usd_per_rune) -> List[
        AlertRunePoolAction]:
        results = []
        if message:
            self.logger.error(f'Empty tx or message in RUNE pool @ #{height}')
            return results

        if message.type != message.MsgDeposit:
            self.logger.error(f'Unexpected message type in RUNE pool tx: {message} @ #{height}')
            return results

        for coin in message.coins:
            if not is_rune(asset := coin['asset']):
                self.logger.error(f'Unexpected asset in RUNE pool tx: {asset}')
                continue

            actor = message.attrs['signer']

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
