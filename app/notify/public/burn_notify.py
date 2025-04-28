from typing import Optional

import pandas as pd
from tqdm import tqdm

from lib.constants import THOR_BLOCK_TIME, THOR_BASIS_POINT_MAX, ADR17_TIMESTAMP, thor_to_float
from lib.cooldown import Cooldown
from lib.date_utils import now_ts, DAY, ts_event_points_to_pandas
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.circ_supply import EventRuneBurn
from models.mimir import MimirTuple
from models.mimir_naming import MIMIR_KEY_MAX_RUNE_SUPPLY, MIMIR_KEY_SYSTEM_INCOME_BURN_RATE
from models.time_series import TimeSeries
from notify.public.block_notify import LastBlockStore


class BurnNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        notify_cd_sec = deps.cfg.as_interval('supply.rune_burn.notification.cooldown', '2d')
        self.tally_period = deps.cfg.as_int('supply.rune_burn.notification.tally_period_days', 7) * DAY
        self.cd = Cooldown(self.deps.db, 'RuneBurn', notify_cd_sec)
        self.ts = TimeSeries('RuneMaxSupply', deps.db)

    async def on_data(self, sender, _: MimirTuple):
        if event := await self.get_event():
            if await self.cd.can_do():
                await self.pass_data_to_listeners(event)
                await self.cd.do()

    async def get_event(self) -> Optional[EventRuneBurn]:
        mimir = self.deps.mimir_const_holder
        if not mimir:
            self.logger.error('Mimir constants are not loaded yet!')
            return

        curr_max_supply_8 = mimir[MIMIR_KEY_MAX_RUNE_SUPPLY]
        if not curr_max_supply_8:
            self.logger.error(f'Max supply ({MIMIR_KEY_MAX_RUNE_SUPPLY}) is not set!')
            return

        system_income_burn_bp = int(mimir[MIMIR_KEY_SYSTEM_INCOME_BURN_RATE])
        if not system_income_burn_bp:
            self.logger.error(f'System income burn rate {MIMIR_KEY_SYSTEM_INCOME_BURN_RATE} is not set!')
            return

        if curr_max_supply_8 <= 0:
            # fixes jumps of chart if got "-1" here
            self.logger.error(f'Invalid max supply: {curr_max_supply_8}. Not recording it!')
            return

        # save current max supply (as int, no decimal)
        await self.ts.add(max_supply=curr_max_supply_8)

        # then convert
        curr_max_supply = thor_to_float(curr_max_supply_8)

        # get previous max supply (from tally_period days ago)
        prev_supply = await self.get_supply_time_ago(self.tally_period)
        prev_supply = thor_to_float(prev_supply)

        # get 24h burned rune as sum of last 24h deltas
        supply_24h_ago = await self.get_supply_time_ago(DAY)
        supply_24h_ago = thor_to_float(supply_24h_ago)
        last_24h_burned_rune = max(0.0, supply_24h_ago - curr_max_supply)

        supply_info = await self.deps.rune_market_fetcher.get_full_supply_info()

        all_points = await self.get_last_supply_dataframe()
        all_points_resampled = await self.resample(all_points)
        points_deltas = self._extract_only_burned_rune_delta(all_points_resampled)

        return EventRuneBurn(
            curr_max_rune=curr_max_supply,
            prev_max_rune=prev_supply,
            points=points_deltas,
            usd_per_rune=self.deps.price_holder.usd_per_rune,
            system_income_burn_percent=system_income_burn_bp / THOR_BASIS_POINT_MAX * 100.0,
            period_seconds=self.cd.cooldown,
            start_ts=ADR17_TIMESTAMP,
            tally_days=self.tally_period / DAY,
            circulating_suppy=supply_info.circulating,
            last_24h_burned_rune=last_24h_burned_rune,
        )

    async def get_last_supply_dataframe(self):
        all_points = await self.ts.get_last_points(self.tally_period)
        df = ts_event_points_to_pandas(all_points, shift_time=False)
        df["t"] = pd.to_datetime(df["t"], unit='s')
        df['max_supply'] = df['max_supply'].apply(thor_to_float)
        df['max_supply_delta'] = -df['max_supply'].diff().fillna(0)
        return df

    @staticmethod
    async def resample(df, period='4h'):
        df = df.resample(period, on='t').sum()
        return df

    @staticmethod
    def _extract_only_burned_rune_delta(df: pd.DataFrame):
        """
        Extract only burned rune delta from the dataframe
        Returns list of tuples (timestamp, burned_rune_delta)
        """
        row = df['max_supply_delta']
        timestamps = row.index
        return [
            (int(ts.timestamp()), value)
            for ts, value in zip(timestamps, row)
        ]

    async def get_last_supply_float(self):
        return await self.ts.get_last_value('max_supply')

    async def erase_and_populate_from_history(self, period=60, max_points=1000):
        last_block = self.deps.last_block_store.thor
        if not last_block:
            self.logger.error('Last block is not set!')
            return

        await self.ts.clear()

        total_time = period * max_points
        block = last_block - total_time / THOR_BLOCK_TIME
        block_step = period / THOR_BLOCK_TIME
        ts = now_ts() - total_time

        for _ in tqdm(range(int(max_points))):
            max_supply = await self.get_supply_at_block(block)
            await self.ts.add_ts(ts, max_supply=max_supply)

            self.logger.info(f"block: {block}, ts: {ts}, max_supply: {max_supply}")

            block += block_step
            ts += period
            if block < 0:
                break

    async def get_supply_at_block(self, block: int):
        mimir = await self.deps.thor_connector.query_mimir(height=int(block))
        return mimir[MIMIR_KEY_MAX_RUNE_SUPPLY] if mimir else None

    async def get_supply_time_ago(self, sec_ago: float, tolerance_percent=10):
        data, _ = await self.ts.get_best_point_ago(sec_ago, tolerance_percent=tolerance_percent)
        if data and 'max_supply' in data:
            return data['max_supply']
        else:
            store: LastBlockStore = self.deps.last_block_store
            block = store.block_time_ago(sec_ago)
            return await self.get_supply_at_block(block)
