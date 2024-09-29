from datetime import datetime, timedelta

from proto.access import NativeThorTx
from jobs.scanner.block_loader import BlockResult
from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.memo import THORMemo
from lib.money import pretty_dollar


class AffiliateRecorder(WithLogger, INotified):
    def __init__(self, deps: DepContainer, key_prefix="tx"):
        super().__init__()
        self.deps = deps
        self.redis = deps.db.redis
        self.key_prefix = key_prefix
        self.days_to_keep = 60
        self.clear_every_ticks = 10
        self._clear_counter = 0

    @staticmethod
    def _date_format(date):
        return date.strftime('%d.%m.%Y')

    async def clear_old_events(self, days, look_back=90):
        cutoff_time = datetime.now() - timedelta(days=days)
        fail_count = 0
        total_deleted = 0
        while True:
            keys = await self.redis.keys(self._prefixed_key('*', cutoff_time))
            if keys:
                await self.redis.delete(*keys)
                total_deleted += len(keys)
            else:
                fail_count += 1
                if fail_count > look_back:
                    break

            cutoff_time -= timedelta(days=1)

        self.logger.info(f"Deleted {total_deleted} old swap events older than {days} days")

    def _prefixed_key(self, route, date):
        return f"{self.key_prefix}:aff_collector:{route}:{self._date_format(date)}"

    @staticmethod
    def get_affiliate_name(memo: THORMemo):
        affiliate_name = memo.affiliate_address.lower()
        return affiliate_name

    async def store_event(self, memo: THORMemo, volume_usd, dt: datetime):
        if volume_usd <= 0:
            return

        aff = self.get_affiliate_name(memo)
        key = self._prefixed_key(aff, dt)

        affiliate_fee = memo.affiliate_fee_0_1 * volume_usd

        await self.redis.hincrbyfloat(key, "volume", affiliate_fee)
        self.logger.debug(f"Stored swap event: {key} for {aff}: {pretty_dollar(affiliate_fee)} at {dt}")

    async def _process_aff_tx(self, tx: NativeThorTx, memo: THORMemo):
        # tx_data
        pass
        # print(f'Found affiliate address: {memo.affiliate_address} in tx: {tx.hash} type: {memo.action}')

    async def on_data(self, sender, data: BlockResult):
        for tx in data.txs:
            try:
                if tx.memo:
                    memo = THORMemo.parse_memo(tx.memo)
                    if memo.affiliate_address:
                        await self._process_aff_tx(tx, memo)
            except Exception as e:
                self.logger.error(f'Error {e!r} processing tx: {tx.hash} at block #{data.block_no}')

        # Sometimes we need to clear old dates
        await self.clear_old_events(self.days_to_keep)
