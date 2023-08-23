import datetime
from contextlib import suppress
from typing import List

from services.lib.accumulator import Accumulator
from services.lib.date_utils import HOUR
from services.lib.delegates import WithDelegates, INotified
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.events import EventSwap
from services.models.tx import ThorTx
from services.models.tx_type import TxType


class VolumeRecorder(WithDelegates, INotified, WithLogger):
    KEY_SWAP = 'swap'
    KEY_SWAP_SYNTH = 'synth'
    KEY_ADD_LIQUIDITY = 'add'
    KEY_WITHDRAW_LIQUIDITY = 'withdraw'

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        t = deps.cfg.as_interval('price.volume.record_tolerance', HOUR)
        self._accumulator = Accumulator('Volume', deps.db, tolerance=t)

    async def on_data(self, sender, txs: List[ThorTx]):
        with suppress(Exception):
            total_volume = await self.handle_txs_unsafe(txs)
            await self.pass_data_to_listeners(total_volume, self)

    async def handle_txs_unsafe(self, txs):
        current_price = self.deps.price_holder.usd_per_rune or 0.01
        total_volume = 0.0
        for tx in txs:
            volume = tx.full_rune
            if volume > 0:
                swap, synth = 0.0, 0.0
                if tx.type == TxType.SWAP:
                    swap = volume
                    if tx.is_synth_involved:
                        synth = volume

                add = volume if tx.type == TxType.ADD_LIQUIDITY else 0.0
                withdraw = volume if tx.type == TxType.WITHDRAW else 0.0

                await self._add_point(tx.date_timestamp, add, swap, synth, withdraw, current_price)

                total_volume += volume

        return total_volume

    async def _add_point(self, date_timestamp, add, swap, synth, withdraw, current_price):
        await self._accumulator.add(
            date_timestamp,
            **{
                self.KEY_SWAP: swap,
                self.KEY_SWAP_SYNTH: synth,
                self.KEY_ADD_LIQUIDITY: add,
                self.KEY_WITHDRAW_LIQUIDITY: withdraw,
            }
        )
        await self._accumulator.set(
            date_timestamp,
            price=current_price,  # it is better to get price at the tx's block!
        )

    async def get_data_instant(self, ts=None):
        return await self._accumulator.get(ts)

    async def get_data_range_ago(self, ago):
        return await self._accumulator.get_range(-ago)

    async def get_data_range_ago_n(self, ago, n=30):
        return await self._accumulator.get_range_n(-ago, n=n)


class VolumeRecorderSwapEvent(VolumeRecorder):
    def __init__(self, deps: DepContainer):
        super().__init__(deps)

    async def on_data(self, sender, events: List[EventSwap]):
        with suppress(Exception):
            total_volume = await self.handle_txs_unsafe(events)
            await self.pass_data_to_listeners(total_volume, self)

    async def handle_txs_unsafe(self, events: List[EventSwap], ts=None):
        ph = self.deps.price_holder
        ts = datetime.datetime.now().timestamp()
        for event in events:
            usd_value = ph.convert_to_usd(event.amount, event.asset)
            is_synth = '/' in event.asset

            synth_volume = usd_value if is_synth else usd_value
            await self._add_point(ts, 0.0, usd_value, synth_volume, 0.0, ph.usd_per_rune)
