from typing import List

from services.lib.accumulator import Accumulator
from services.lib.date_utils import HOUR
from services.lib.delegates import WithDelegates, INotified
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.tx import ThorTxExtended, ThorTxType


class VolumeRecorder(WithDelegates, INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        t = deps.cfg.as_interval('price.volume.record_tolerance', HOUR)
        self._accumulator = Accumulator('Volume', deps.db, tolerance=t)

    async def on_data(self, sender, txs: List[ThorTxExtended]):
        current_price = self.deps.price_holder.usd_per_rune or 0.01
        total_volume = 0.0
        for tx in txs:
            volume = tx.full_rune
            if volume > 0:
                synth = volume if tx.is_synth_involved else 0.0
                swap = volume if tx.type == ThorTxType.TYPE_SWAP else 0.0
                add = volume if tx.type == ThorTxType.TYPE_ADD_LIQUIDITY else 0.0
                withdraw = volume if tx.type == ThorTxType.TYPE_WITHDRAW else 0.0
                await self._accumulator.add(
                    tx.date_timestamp,
                    synth=synth,
                    swap=swap,
                    add=add,
                    withdraw=withdraw,
                )
                total_volume += volume
                await self._accumulator.set(
                    tx.date_timestamp,
                    price=current_price,  # it is better to get price at the tx's block!
                )

        print('-------')
        print(f'{total_volume = }')
        # print(await self._accumulator.get())
        print(await self.get_data_range_ago_n(HOUR * 3, 2))
        # await self._accumulator.get_range_n()

    async def get_data_instant(self, ts=None):
        return await self._accumulator.get(ts)

    async def get_data_range_ago(self, ago):
        return await self._accumulator.get_range(-ago)

    async def get_data_range_ago_n(self, ago, n=30):
        return await self._accumulator.get_range_n(-ago, n=n)
