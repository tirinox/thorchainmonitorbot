from collections import defaultdict
from contextlib import suppress
from typing import List, Tuple

from services.lib.accumulator import Accumulator
from services.lib.active_users import DailyActiveUserCounter
from services.lib.date_utils import HOUR, now_ts
from services.lib.delegates import WithDelegates, INotified
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.memo import ActionType
from services.models.tx import ThorTx
from services.models.vol_n import TxCountStats, TxMetricType


class TxCountRecorder(WithDelegates, INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        r = deps.db.redis
        self._counters = {
            TxMetricType.SWAP: DailyActiveUserCounter(r, 'AllSwaps'),
            TxMetricType.TRADE_SWAP: DailyActiveUserCounter(r, 'TradeSwaps'),
            TxMetricType.TRADE_DEPOSIT: DailyActiveUserCounter(r, 'TradeDeposit'),
            TxMetricType.TRADE_WITHDRAWAL: DailyActiveUserCounter(r, 'TradeWithdrawal'),
            TxMetricType.SWAP_SYNTH: DailyActiveUserCounter(r, 'SynthSwaps'),
            TxMetricType.STREAMING: DailyActiveUserCounter(r, 'StreamingSwaps'),
        }

    async def _write_tx_count(self, txs: List[ThorTx]):
        unique_tx_hashes = defaultdict(set)

        for tx in txs:
            if not tx or not (ident := tx.tx_hash):
                continue

            if tx.type == ActionType.SWAP:
                if tx.is_trade_asset_involved:
                    unique_tx_hashes.get(TxMetricType.TRADE_SWAP).add(ident)
                if tx.is_synth_involved:
                    unique_tx_hashes.get(TxMetricType.SWAP_SYNTH).add(ident)
                if tx.is_streaming:
                    unique_tx_hashes.get(TxMetricType.STREAMING).add(ident)
                unique_tx_hashes.get(TxMetricType.SWAP).add(ident)
            elif tx.type == ActionType.TRADE_ACC_DEPOSIT:
                unique_tx_hashes.get(TxMetricType.TRADE_DEPOSIT).add(ident)
            elif tx.type == ActionType.TRADE_ACC_WITHDRAW:
                unique_tx_hashes.get(TxMetricType.TRADE_WITHDRAWAL).add(ident)
            elif tx.type == ActionType.ADD_LIQUIDITY:
                unique_tx_hashes.get(TxMetricType.ADD_LIQUIDITY).add(ident)
            elif tx.type == ActionType.WITHDRAW:
                unique_tx_hashes.get(TxMetricType.WITHDRAW_LIQUIDITY).add(ident)

        for tx_type, tx_set in unique_tx_hashes.values():
            if tx_set:
                await self._counters[tx_type].hit(users=tx_set)

    async def on_data(self, sender, txs: List[ThorTx]):
        try:
            await self._write_tx_count(txs)
            await self.pass_data_to_listeners(txs)  # pass the data unchanged to the next subscribers
        except Exception:
            self.logger.exception('Error while writing tx count')

    async def get_stats(self, period_days=7):
        curr_dict, prev_dict = defaultdict(int), defaultdict(int)
        for tx_type, counter in self._counters.values():
            curr, prev = await counter.get_current_and_previous_au(period_days)
            curr_dict[tx_type] += curr
            prev_dict[tx_type] += prev

        return TxCountStats(curr_dict, prev_dict)


class VolumeRecorder(WithDelegates, INotified, WithLogger):
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

        volumes = defaultdict(float)
        ts = None
        for tx in txs:
            volume = tx.full_rune
            if volume > 0:
                if tx.type == ActionType.SWAP:
                    volumes[TxMetricType.SWAP] += volume
                    if tx.is_synth_involved:
                        volumes[TxMetricType.SWAP_SYNTH] += volume
                    if tx.is_trade_asset_involved:
                        volumes[TxMetricType.TRADE_SWAP] += volume
                    if tx.is_streaming:
                        volumes[TxMetricType.STREAMING] += volume
                elif tx.type == ActionType.TRADE_ACC_DEPOSIT:
                    volumes[TxMetricType.TRADE_DEPOSIT] += volume
                elif tx.type == ActionType.TRADE_ACC_WITHDRAW:
                    volumes[TxMetricType.TRADE_WITHDRAWAL] += volume
                elif tx.type == ActionType.ADD_LIQUIDITY:
                    volumes[TxMetricType.ADD_LIQUIDITY] += volume
                elif tx.type == ActionType.WITHDRAW:
                    volumes[TxMetricType.WITHDRAW_LIQUIDITY] += volume

                total_volume += volume
                ts = tx.date_timestamp

        if ts is not None:
            await self._add_point(ts, volumes, current_price)

        return total_volume

    async def _add_point(self, date_timestamp, volumes, current_price: float):
        self.logger.info(f'Update {date_timestamp}: {volumes}')
        await self._accumulator.add(
            date_timestamp,
            **volumes
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
                s[TxMetricType.usd_key(k)] += v * price

        return s

    async def get_previous_and_current_sum(self, period_sec, now=0) -> Tuple[dict, dict]:
        now = now or now_ts()
        curr_volume_stats = await self.get_sum(now - period_sec, now)
        prev_volume_stats = await self.get_sum(now - period_sec * 2, now - period_sec)
        return curr_volume_stats, prev_volume_stats

    async def get_data_range_ago_n(self, ago, n=30):
        return await self._accumulator.get_range_n(-ago, n=n)
