from collections import defaultdict
from contextlib import suppress
from typing import List, NamedTuple

from services.lib.accumulator import Accumulator
from services.lib.active_users import DailyActiveUserCounter
from services.lib.date_utils import HOUR
from services.lib.delegates import WithDelegates, INotified
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.memo import ActionType
from services.models.tx import ThorTx


class TxCountStat(NamedTuple):
    count_curr: int
    count_prev: int


class TxCountStats(NamedTuple):
    all_swap: TxCountStat
    trade: TxCountStat
    synth: TxCountStat
    streaming: TxCountStat


class TxCountRecorder(WithDelegates, INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        r = deps.db.redis
        self._all_swap_counter = DailyActiveUserCounter(r, 'AllSwaps')
        self._trade_swap_counter = DailyActiveUserCounter(r, 'TradeSwaps')
        self._synth_swap_counter = DailyActiveUserCounter(r, 'SynthSwaps')
        self._streaming_swap_counter = DailyActiveUserCounter(r, 'StreamingSwaps')

    async def _write_tx_count(self, txs: List[ThorTx]):
        normal_swaps = set()
        trade_swaps = set()
        synth_swaps = set()
        streaming_swaps = set()

        for tx in txs:
            if tx.type == ActionType.SWAP:
                ident = tx.tx_hash
                if tx.is_trade_asset_involved:
                    trade_swaps.add(ident)
                if tx.is_synth_involved:
                    synth_swaps.add(ident)
                if tx.is_streaming:
                    streaming_swaps.add(ident)
                normal_swaps.add(ident)

        await self._all_swap_counter.hit(users=normal_swaps)
        await self._trade_swap_counter.hit(users=trade_swaps)
        await self._synth_swap_counter.hit(users=synth_swaps)
        await self._streaming_swap_counter.hit(users=streaming_swaps)

    async def on_data(self, sender, txs: List[ThorTx]):
        try:
            await self._write_tx_count(txs)
            await self.pass_data_to_listeners(txs)  # pass the data unchanged to the next subscribers
        except Exception:
            self.logger.exception('Error while writing tx count')

    @staticmethod
    async def _get_curr_prev(counter: DailyActiveUserCounter, days):
        curr, prev = await counter.get_current_and_previous_au(days)
        return TxCountStat(curr, prev)

    async def get_stats(self, period_days=7):
        return TxCountStats(
            all_swap=await self._get_curr_prev(self._all_swap_counter, period_days),
            trade=await self._get_curr_prev(self._trade_swap_counter, period_days),
            synth=await self._get_curr_prev(self._synth_swap_counter, period_days),
            streaming=await self._get_curr_prev(self._streaming_swap_counter, period_days)
        )


class VolumeRecorder(WithDelegates, INotified, WithLogger):
    KEY_SWAP = 'swap'
    KEY_SWAP_SYNTH = 'synth'
    KEY_ADD_LIQUIDITY = 'add'
    KEY_WITHDRAW_LIQUIDITY = 'withdraw'
    KEY_TRADE_ASSET = 'trade_asset'

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        t = deps.cfg.as_interval('price.volume.record_tolerance', HOUR)

        # todo: auto clean
        self._accumulator = Accumulator('Volume', deps.db, tolerance=t)

    async def on_data(self, sender, txs: List[ThorTx]):
        with suppress(Exception):
            await self.handle_txs_unsafe(txs)

            await self.pass_data_to_listeners(txs)  # pass the data unchanged to the next subscribers

    async def handle_txs_unsafe(self, txs: List[ThorTx]):
        current_price = self.deps.price_holder.usd_per_rune or 0.01
        total_volume = 0.0
        swap, synth, add, withdraw, trade = 0.0, 0.0, 0.0, 0.0, 0.0
        ts = None
        for tx in txs:
            volume = tx.full_rune
            if volume > 0:
                if tx.type == ActionType.SWAP:
                    swap += volume
                    if tx.is_synth_involved:
                        synth += volume
                    if tx.is_trade_asset_involved:
                        trade += volume
                elif tx.type == ActionType.ADD_LIQUIDITY:
                    add += volume
                elif tx.type == ActionType.WITHDRAW:
                    withdraw += volume

                total_volume += volume
                ts = tx.date_timestamp

        if ts is not None:
            await self._add_point(ts, add, swap, synth, withdraw, trade, current_price)

        return total_volume

    async def _add_point(self, date_timestamp,
                         add: float, swap: float, synth: float,
                         withdraw: float, trade: float, current_price: float):
        self.logger.info(f'Update {date_timestamp}: '
                         f'{add = :.0f}, {swap = :.0f}, {synth = :.0f}, '
                         f'{withdraw = :.0f}')
        await self._accumulator.add(
            date_timestamp,
            **{
                self.KEY_SWAP: swap,
                self.KEY_SWAP_SYNTH: synth,
                self.KEY_ADD_LIQUIDITY: add,
                self.KEY_WITHDRAW_LIQUIDITY: withdraw,
                self.KEY_TRADE_ASSET: trade,
            }
        )
        await self._accumulator.set(
            date_timestamp,
            price=current_price,  # it is better to get price at the tx's block!
        )

    async def get_data_instant(self, ts=None):
        return await self._accumulator.get(ts)

    async def get_data_range_ago(self, ago_sec) -> dict[float, dict[str, float]]:
        # timestamp -> {key -> value}
        return await self._accumulator.get_range(-ago_sec)

    async def get_sum(self, start_ts, end_ts) -> dict[str, float]:
        range_data = await self._accumulator.get_range(start_ts, end_ts)
        # sum all dict values for each key
        s = defaultdict(float)
        for d in range_data.values():
            price = d.pop('price', 0.0)
            for k, v in d.items():
                s[k] += v
                s[f'{k}_usd'] += v * price

        return s

    async def get_data_range_ago_n(self, ago, n=30):
        return await self._accumulator.get_range_n(-ago, n=n)
