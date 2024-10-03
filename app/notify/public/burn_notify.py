from tqdm import tqdm

from jobs.fetch.mimir import MimirTuple
from lib.constants import THOR_BLOCK_TIME
from lib.cooldown import Cooldown
from lib.date_utils import now_ts
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.utils import WithLogger
from models.circ_supply import RuneBurnEvent
from models.mimir_naming import MIMIR_KEY_MAX_RUNE_SUPPLY
from models.time_series import TimeSeries


class BurnNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        notify_cd_sec = deps.cfg.as_interval('supply.rune_burn.notification.cooldown', '2d')
        self.cd = Cooldown(self.deps.db, 'RuneBurn', notify_cd_sec)
        self.ts = TimeSeries('RuneMaxSupply', deps.db)

    async def on_data(self, sender, event: MimirTuple):
        mimir = self.deps.mimir_const_holder
        if not mimir:
            self.logger.error('Mimir constants are not loaded yet!')
            return

        max_supply = mimir[MIMIR_KEY_MAX_RUNE_SUPPLY]
        if not max_supply:
            self.logger.error(f'Max supply ({MIMIR_KEY_MAX_RUNE_SUPPLY}) is not set!')
            return

        await self.ts.add(max_supply=max_supply)

        if await self.cd.can_do():
            await self.pass_data_to_listeners(RuneBurnEvent(
                500_000_000,
                500_000_000,
                period_seconds=self.cd.cooldown
            ))
            await self.cd.do()

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
            mimir = await self.deps.thor_connector.query_mimir(height=int(block))
            max_supply = mimir[MIMIR_KEY_MAX_RUNE_SUPPLY]
            await self.ts.add_ts(ts, max_supply=max_supply)

            print(f"block: {block}, ts: {ts}, max_supply: {max_supply}")

            block += block_step
            ts += period
            if block < 0:
                break
