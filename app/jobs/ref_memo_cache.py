import json
from typing import Iterable, Optional

from api.aionode.types import ThorException, ThorMemoReference
from jobs.scanner.block_result import BlockResult
from jobs.scanner.event_db import EventDbTxDeduplicator
from jobs.scanner.tx import NativeThorTx
from lib.date_utils import HOUR
from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.memo import THORMemo, ActionType


class RefMemoCache(INotified, WithLogger):
    """
    Block-scanner listener that discovers REFERENCE memo registration txs,
    resolves their numeric reference id via THORNode, and persists the result
    in Redis for fast lookup by reference id.
    """

    REDIS_KEY_BY_ID = 'Memo:Reference:ById'
    REDIS_KEY_BY_REGISTRATION_HASH = 'Memo:Reference:ByRegistrationHash'
    DEDUP_COMPONENT_NAME = 'ref_memo_cache'
    CACHE_TTL_SEC = 6 * HOUR

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self._dedup = EventDbTxDeduplicator(deps.db, self.DEDUP_COMPONENT_NAME)

    @staticmethod
    def parse_reference_memo(memo: str) -> Optional[THORMemo]:
        if not memo:
            return None

        try:
            parsed = THORMemo.parse_memo(memo, no_raise=True)
        except Exception:
            return None

        if parsed and parsed.action == ActionType.REFERENCE:
            return parsed
        return None

    @classmethod
    def is_reference_tx(cls, tx: NativeThorTx) -> bool:
        return bool(tx and tx.tx_hash and cls.parse_reference_memo(tx.memo))

    @classmethod
    def iter_reference_txs(cls, block: BlockResult) -> Iterable[NativeThorTx]:
        for tx in block.txs:
            if cls.is_reference_tx(tx):
                yield tx

    @staticmethod
    def _serialize_reference(ref: ThorMemoReference) -> str:
        return json.dumps(ref._asdict(), sort_keys=True)

    @staticmethod
    def _deserialize_reference(raw) -> Optional[ThorMemoReference]:
        if not raw:
            return None

        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                return None

        if isinstance(raw, dict):
            return ThorMemoReference.from_json(raw)
        return None

    async def _redis(self):
        return await self.deps.db.get_redis()

    @classmethod
    def key_by_reference_id(cls, reference_id) -> str:
        return f'{cls.REDIS_KEY_BY_ID}:{reference_id}'

    @classmethod
    def key_by_registration_hash(cls, registration_hash: str) -> str:
        return f'{cls.REDIS_KEY_BY_REGISTRATION_HASH}:{registration_hash}'

    async def cache_reference(self, ref: ThorMemoReference):
        redis = await self._redis()
        ref_id = str(ref.reference)
        ref_key = self.key_by_reference_id(ref_id)

        await redis.set(ref_key, self._serialize_reference(ref))
        await redis.expire(ref_key, int(self.CACHE_TTL_SEC))

        if ref.registration_hash:
            reg_key = self.key_by_registration_hash(ref.registration_hash)
            await redis.set(reg_key, ref_id)
            await redis.expire(reg_key, int(self.CACHE_TTL_SEC))

    async def get_by_reference_id(self, reference_id) -> Optional[ThorMemoReference]:
        redis = await self._redis()
        raw = await redis.get(self.key_by_reference_id(reference_id))
        return self._deserialize_reference(raw)

    async def get_memo(self, reference_id) -> str:
        memo_ref = await self.get_by_reference_id(reference_id)
        return memo_ref.memo if memo_ref else ''

    async def get_reference_id_by_registration_hash(self, registration_hash: str) -> int:
        if not registration_hash:
            return 0

        redis = await self._redis()
        raw = await redis.get(self.key_by_registration_hash(registration_hash))
        try:
            return int(raw or 0)
        except (TypeError, ValueError):
            return 0

    async def clear_all(self):
        redis = await self._redis()
        keys = await redis.keys(self.key_by_reference_id('*'))
        keys.extend(await redis.keys(self.key_by_registration_hash('*')))
        if keys:
            await redis.delete(*keys)

    async def on_data(self, sender, data: BlockResult):
        reference_txs = [tx for tx in self.iter_reference_txs(data)]
        if not reference_txs:
            return

        tx_hashes = [tx.tx_hash for tx in reference_txs if tx.tx_hash]
        new_hashes = set(await self._dedup.only_new_hashes(tx_hashes))
        cached_count = 0

        for tx in reference_txs:
            if tx.tx_hash not in new_hashes:
                continue

            if await self.get_reference_id_by_registration_hash(tx.tx_hash):
                await self._dedup.mark_as_seen(tx.tx_hash)
                continue

            try:
                memo_ref = await self.deps.thor_connector.query_memo_reference(tx.tx_hash)
            except ThorException as e:
                self.logger.warning(
                    f'Failed to resolve reference memo for tx {tx.tx_hash}: '
                    f'code={e.code} message={e.message}'
                )
                continue
            except Exception as e:
                self.logger.warning(f'Failed to resolve reference memo for tx {tx.tx_hash}: {e!r}')
                continue

            await self.cache_reference(memo_ref)
            await self._dedup.mark_as_seen(tx.tx_hash)
            cached_count += 1

        if cached_count:
            self.logger.info(
                f'RefMemoCache stored {cached_count} reference memo(s) from block #{data.block_no}'
            )

