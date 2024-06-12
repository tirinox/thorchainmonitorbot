import asyncio
from typing import List

from redis import Redis

from services.lib.cooldown import Cooldown
from services.lib.db import DB
from services.lib.logs import WithLogger
from services.models.tx import ThorTx


class TxDeduplicator(WithLogger):
    def __init__(self, db: DB, key):
        super().__init__()
        self.db = db
        self._key = key

    async def mark_as_seen(self, tx_id):
        if not tx_id:
            return

        r: Redis = self.db.redis
        await r.sadd(self._key, tx_id)

    async def forget(self, tx_id):
        if not tx_id:
            return
        r: Redis = self.db.redis
        return await r.srem(self._key, tx_id)

    async def have_ever_seen(self, tx: ThorTx):
        if not tx or not tx.tx_hash:
            return True
        return await self.have_ever_seen_hash(tx.tx_hash)

    async def have_ever_seen_hash(self, tx_id):
        if not tx_id:
            return True
        r: Redis = self.db.redis
        return await r.sismember(self._key, tx_id)

    async def batch_ever_seen_hashes(self, txs: List[str]):
        return await asyncio.gather(*[self.have_ever_seen_hash(tx_hash) for tx_hash in txs])

    async def only_new_transaction_hashes(self, txs: List[str], silent=False):
        flags = await self.batch_ever_seen_hashes(txs)
        tmp_txs = []
        for flag, tx in zip(flags, txs):
            if flag:
                if not silent:
                    self.logger.warning(f'Tx {tx.tx_hash} ({tx.type}) has been already announced. Ignore!')
            else:
                tmp_txs.append(tx)
        return tmp_txs

    async def only_new_transactions(self, txs: List[ThorTx]):
        hashes = [(tx.tx_hash if tx else None) for tx in txs]
        return await self.only_new_transaction_hashes(hashes)

    async def clear(self):
        r: Redis = self.db.redis
        await r.delete(self._key)


class TxDeduplicatorSenderCooldown(TxDeduplicator):
    def __init__(self, db: DB, key, cooldown_key_prefix, cooldown_sec=60, ):
        super().__init__(db, key)
        self._cooldown_key_prefix = cooldown_key_prefix
        self._cooldown_sec = cooldown_sec

    async def have_ever_seen(self, tx: ThorTx):
        if not tx or not tx.tx_hash:
            return True

        # for each sender, we have a separate cooldown
        event_name = f'{self._cooldown_key_prefix}-{tx.sender_address}'
        sender_cd = Cooldown(self.db, event_name, self._cooldown_sec)
        if not await sender_cd.can_do():
            self.logger.warning(f'[{self._cooldown_key_prefix}] Sender cooldown went off for {tx.sender_address}!')
            return True

        await sender_cd.do()
        return False
