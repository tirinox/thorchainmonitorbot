import asyncio
from typing import List

from redis import Redis

from lib.bloom_filt import BloomFilter
from lib.cooldown import Cooldown
from lib.db import DB
from lib.logs import WithLogger
from models.tx import ThorTx


class TxDeduplicator(WithLogger):
    def __init__(self, db: DB, key, capacity=100000, error_rate=0.001):
        super().__init__()
        self.db = db

        assert capacity > 10
        assert 0.0001 < error_rate < 0.1
        assert key and isinstance(key, str)

        full_key = f'tx:dedup_v2:{key}'
        self._bf = BloomFilter(self.db.redis, full_key, capacity, error_rate)

    @property
    def key(self):
        return self._bf.redis_key

    async def mark_as_seen(self, tx_id):
        if not tx_id:
            return
        await self._bf.add(tx_id)

    async def mark_as_seen_txs(self, txs: List[ThorTx]):
        for tx in txs:
            if tx and tx.tx_hash:
                await self.mark_as_seen(tx.tx_hash)

    async def forget(self, tx_id):
        raise NotImplementedError

    async def have_ever_seen(self, tx: ThorTx):
        if not tx or not tx.tx_hash:
            return True
        return await self.have_ever_seen_hash(tx.tx_hash)

    async def have_ever_seen_hash(self, tx_id):
        if not tx_id:
            return True
        return await self._bf.contains(tx_id)

    async def batch_ever_seen_hashes(self, txs: List[str]):
        return await asyncio.gather(*[self.have_ever_seen_hash(tx_hash) for tx_hash in txs])

    async def only_hashes_having_certain_flag(self, txs: List[str], desired_flag) -> List[str]:
        flags = await self.batch_ever_seen_hashes(txs)
        tmp_txs_hashes = []
        desired_flag = bool(desired_flag)
        for flag, tx_id in zip(flags, txs):
            if bool(flag) == desired_flag:
                tmp_txs_hashes.append(tx_id)
        return tmp_txs_hashes

    async def only_txs_having_certain_flag(self, txs: List[ThorTx], desired_flag) -> List[ThorTx]:
        tx_dict = {tx.tx_hash: tx for tx in txs if tx and tx.tx_hash}
        filtered_tx_hashes = set(await self.only_hashes_having_certain_flag(list(tx_dict.keys()), desired_flag))
        return [tx for tx in tx_dict.values() if tx.tx_hash in filtered_tx_hashes]

    async def only_new_hashes(self, txs: List[str]) -> List[str]:
        return await self.only_hashes_having_certain_flag(txs, False)

    async def only_seen_hashes(self, txs: List[str]) -> List[str]:
        return await self.only_hashes_having_certain_flag(txs, True)

    async def only_new_txs(self, txs: List[ThorTx], logs=False) -> List[ThorTx]:
        len_in = len(txs)
        results = await self.only_txs_having_certain_flag(txs, False)
        if logs and len(results) != len_in:
            self.logger.info(f'(k={self.key}) Filtered {len_in} txs to {len(results)} new txs.')
        return results

    async def only_seen_txs(self, txs: List[ThorTx]) -> List[ThorTx]:
        return await self.only_txs_having_certain_flag(txs, True)

    async def clear(self):
        r: Redis = self.db.redis
        await r.delete(self.key)


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
