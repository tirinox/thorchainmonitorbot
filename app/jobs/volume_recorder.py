from collections import defaultdict
from typing import List, Tuple, Union

from lib.accumulator import Accumulator
from lib.active_users import DailyActiveUserCounter
from lib.date_utils import HOUR, now_ts
from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.utils import WithLogger
from models.memo import ActionType
from models.runepool import AlertRunePoolAction
from models.trade_acc import AlertTradeAccountAction
from models.tx import ThorTx
from models.vol_n import TxCountStats, TxMetricType
from notify.dup_stop import TxDeduplicator


def convert_trade_actions_to_txs(txs, d: DepContainer) -> List[ThorTx]:
    """
    The classes below are able to handle both ThorTx and AlertTradeAccountAction, AlertRunePoolAction
     thanks to this function.

    If the input is an AlertTradeAccountAction, convert it to a list of single ThorTx.
    Otherwise, return the input as is. (List[ThorTx])
    """
    if isinstance((event := txs), (AlertTradeAccountAction, AlertRunePoolAction)):
        tx = event.as_thor_tx
        tx.calc_full_rune_amount(d.price_holder.pool_info_map)
        tx.height = int(d.last_block_store)
        tx.date = int(now_ts() * 1e9)
        return [tx]
    else:
        return txs


class TxCountRecorder(INotified, WithLogger):
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
            TxMetricType.WITHDRAW_LIQUIDITY: DailyActiveUserCounter(r, 'Withdraw'),
            TxMetricType.ADD_LIQUIDITY: DailyActiveUserCounter(r, 'AddLiquidity'),
            TxMetricType.RUNEPOOL_ADD: DailyActiveUserCounter(r, 'RunePoolDeposit'),
            TxMetricType.RUNEPOOL_WITHDRAW: DailyActiveUserCounter(r, 'RunePoolWithdraw'),
        }
        self._deduplicator = TxDeduplicator(deps.db, 'TxCount')

    async def _write_tx_count(self, txs: List[ThorTx]):
        unique_tx_hashes = defaultdict(set)
        for tx in txs:
            if not tx or not (ident := tx.tx_hash):
                continue

            if tx.is_of_type(ActionType.SWAP):
                if tx.is_trade_asset_involved:
                    unique_tx_hashes[TxMetricType.TRADE_SWAP].add(ident)
                if tx.is_synth_involved:
                    unique_tx_hashes[TxMetricType.SWAP_SYNTH].add(ident)
                if tx.is_streaming:
                    unique_tx_hashes[TxMetricType.STREAMING].add(ident)
                unique_tx_hashes[TxMetricType.SWAP].add(ident)
            elif tx.is_of_type(ActionType.TRADE_ACC_DEPOSIT):
                unique_tx_hashes[TxMetricType.TRADE_DEPOSIT].add(ident)
            elif tx.is_of_type(ActionType.TRADE_ACC_WITHDRAW):
                unique_tx_hashes[TxMetricType.TRADE_WITHDRAWAL].add(ident)
            elif tx.is_of_type(ActionType.ADD_LIQUIDITY):
                unique_tx_hashes[TxMetricType.ADD_LIQUIDITY].add(ident)
            elif tx.is_of_type(ActionType.WITHDRAW):
                unique_tx_hashes[TxMetricType.WITHDRAW_LIQUIDITY].add(ident)
            elif tx.is_of_type(ActionType.RUNEPOOL_ADD):
                unique_tx_hashes[TxMetricType.RUNEPOOL_ADD].add(ident)
            elif tx.is_of_type(ActionType.RUNEPOOL_WITHDRAW):
                unique_tx_hashes[TxMetricType.RUNEPOOL_WITHDRAW].add(ident)
            elif tx.is_of_type(ActionType.LOAN_OPEN):
                unique_tx_hashes[TxMetricType.LOAN_OPEN].add(ident)
            elif tx.is_of_type(ActionType.LOAN_CLOSE):
                unique_tx_hashes[TxMetricType.LOAN_CLOSE].add(ident)

        for tx_type, tx_set in unique_tx_hashes.items():
            if tx_set:
                counter = self._counters.get(tx_type)
                if counter:
                    await counter.hit(users=tx_set)
                else:
                    self.logger.error(f'No counter for {tx_type}')

        if unique_tx_hashes:
            self.logger.debug(f'Unique txs written {unique_tx_hashes}')

    async def on_data(self, sender, txs: Union[List[ThorTx], AlertTradeAccountAction]):
        try:
            txs = convert_trade_actions_to_txs(txs, self.deps)
            txs = await self._deduplicator.only_new_txs(txs, logs=True)
            await self._write_tx_count(txs)
            await self._deduplicator.mark_as_seen_txs(txs)
        except Exception as e:
            self.logger.exception('Error while writing tx count', exc_info=e)

    async def get_stats(self, period_days=7):
        curr_dict, prev_dict = defaultdict(int), defaultdict(int)
        for tx_type, counter in self._counters.items():
            curr, prev = await counter.get_current_and_previous_au(period_days)
            curr_dict[tx_type] += curr
            prev_dict[tx_type] += prev

        return TxCountStats(curr_dict, prev_dict)

    async def get_one_metric(self, tx_type, period_days=7):
        counter = self._counters.get(tx_type)
        if counter:
            return await counter.get_current_and_previous_au(period_days)
        return 0, 0


class VolumeRecorder(INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        t = deps.cfg.as_interval('price.volume.record_tolerance', HOUR)

        # todo: auto clean
        self._accumulator = Accumulator('Volume', deps.db, tolerance=t)

        self._deduplicator = TxDeduplicator(deps.db, 'VolumeRecorder')

    async def on_data(self, sender, txs: Union[List[ThorTx], AlertTradeAccountAction]):
        try:
            txs = convert_trade_actions_to_txs(txs, self.deps)
            txs = await self._deduplicator.only_new_txs(txs, logs=True)
            await self.handle_txs_unsafe(txs)
            await self._deduplicator.mark_as_seen_txs(txs)
        except Exception as e:
            self.logger.exception('Error while writing volume', exc_info=e)

    async def handle_txs_unsafe(self, txs: List[ThorTx]):
        current_price = self.deps.price_holder.usd_per_rune or 0.01
        total_volume = 0.0

        volumes = defaultdict(float)
        ts = None
        for tx in txs:
            volume = tx.full_volume_in_rune
            if volume > 0:
                if tx.is_of_type(ActionType.SWAP):
                    volumes[TxMetricType.SWAP] += volume
                    if tx.is_synth_involved:
                        volumes[TxMetricType.SWAP_SYNTH] += volume
                    if tx.is_trade_asset_involved:
                        volumes[TxMetricType.TRADE_SWAP] += volume
                    if tx.is_streaming:
                        volumes[TxMetricType.STREAMING] += volume
                elif tx.is_of_type(ActionType.TRADE_ACC_DEPOSIT):
                    volumes[TxMetricType.TRADE_DEPOSIT] += volume
                elif tx.is_of_type(ActionType.TRADE_ACC_WITHDRAW):
                    volumes[TxMetricType.TRADE_WITHDRAWAL] += volume
                elif tx.is_of_type(ActionType.ADD_LIQUIDITY):
                    volumes[TxMetricType.ADD_LIQUIDITY] += volume
                elif tx.is_of_type(ActionType.WITHDRAW):
                    volumes[TxMetricType.WITHDRAW_LIQUIDITY] += volume
                elif tx.is_of_type(ActionType.RUNEPOOL_ADD):
                    volumes[TxMetricType.RUNEPOOL_ADD] += volume
                elif tx.is_of_type(ActionType.RUNEPOOL_WITHDRAW):
                    volumes[TxMetricType.RUNEPOOL_WITHDRAW] += volume
                elif tx.is_of_type(ActionType.LOAN_OPEN):
                    volumes[TxMetricType.LOAN_OPEN] += volume
                elif tx.is_of_type(ActionType.LOAN_CLOSE):
                    volumes[TxMetricType.LOAN_CLOSE] += volume

                total_volume += volume
                ts = tx.date_timestamp

        if ts is not None:
            await self._add_point(ts, volumes, current_price)

        return total_volume

    async def _add_point(self, date_timestamp, volumes, current_price: float):
        if not volumes:
            return

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
        t0 = now - period_sec * 2
        t1 = now - period_sec

        curr_volume_stats = await self.get_sum(t1, now)
        prev_volume_stats = await self.get_sum(t0, t1)
        return curr_volume_stats, prev_volume_stats

    async def get_latest_distribution_by_asset_type(self, period_sec, now=0) -> dict:
        t1 = now or now_ts()
        t0 = now - period_sec
        s = await self.get_sum(t0, t1)

        total = s.get(TxMetricType.SWAP, 0)
        if total <= 0:
            self.logger.warning(f'Period {t0}..{t1} has no swaps?')
            ordinary, trade, synth, total = 0, 0, 0, 1
        else:
            trade = s.get(TxMetricType.TRADE_SWAP, 0)
            synth = s.get(TxMetricType.SWAP_SYNTH, 0)
            ordinary = total - trade - synth
            if ordinary < 0:
                raise ValueError(f'Swap accounting is broken: ordinary < 0')

        return {
            TxMetricType.SWAP: ordinary / total,
            TxMetricType.SWAP_SYNTH: synth / total,
            TxMetricType.TRADE_SWAP: trade / total
        }

    async def get_data_range_ago_n(self, ago, n=30):
        return await self._accumulator.get_range_n(-ago, n=n)
