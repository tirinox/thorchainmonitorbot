from datetime import datetime, timedelta

from jobs.scanner.block_result import BlockResult
from jobs.scanner.tx import NativeThorTx
from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger
from lib.money import pretty_dollar
from models.memo import THORMemo
from notify.dup_stop import TxDeduplicator


class AffiliateRecorder(WithLogger, INotified):
    def __init__(self, deps: DepContainer, key_prefix="tx"):
        super().__init__()
        self.deps = deps
        self.key_prefix = key_prefix
        self.days_to_keep = 60
        self.clear_every_ticks = 10
        self._clear_counter = 0
        self._dedup = TxDeduplicator(deps.db, 'AffiliateRecorder')

    @staticmethod
    def _date_format(date):
        return date.strftime('%d.%m.%Y')

    async def clear_old_events(self, days, look_back=90):
        cutoff_time = datetime.now() - timedelta(days=days)
        fail_count = 0
        total_deleted = 0
        redis = await self.deps.db.get_redis()
        while True:
            keys = await redis.keys(self._prefixed_key('*', cutoff_time))
            if keys:
                await redis.delete(*keys)
                total_deleted += len(keys)
            else:
                fail_count += 1
                if fail_count > look_back:
                    break

            cutoff_time -= timedelta(days=1)

        self.logger.info(f"Deleted {total_deleted} old swap events older than {days} days")

    def _prefixed_key(self, name, date):
        return f"{self.key_prefix}:aff_collector:{name}:{self._date_format(date)}"

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

        redis = await self.deps.db.get_redis()
        await redis.hincrbyfloat(key, "volume", affiliate_fee)
        self.logger.debug(f"Stored swap event: {key} for {aff}: {pretty_dollar(affiliate_fee)} at {dt}")

    async def _process_aff_tx(self, tx: NativeThorTx, memo: THORMemo):
        print(f'Found affiliate address: {memo.affiliate_address} in tx: {tx.tx_hash} type: {memo.action}')
        print(tx)
        pass  # todo

    async def on_data(self, sender, data: BlockResult):
        """
        Look for events like this:
        {
            "asset": "THOR.RUNE",
            "fee_amount": "166454",
            "fee_bps": "50",
            "gross_amount": "33290900",
            "memo": "=:THOR.RUNE:thor1au0mkysxfh5vvv9g4jtrq78da0kfgqwvx9h33d:0/1/0:rj:50",
            "mode": "EndBlock",
            "rune_address": "thor1zspr6va4ev78lpsh48s57nv6szxj4cdyey34wa",
            "thorname": "rj",
            "tx_id": "5AA7F9DCCED688D7135130079EFA50F25EBAE4237C625648DC1266DB52DF6DB7",
            "type": "affiliate_fee"
        },
        """

        # Sometimes we need to clear old dates
        await self.clear_old_events(self.days_to_keep)
