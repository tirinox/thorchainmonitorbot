from services.lib.constants import BTC_SYMBOL
from services.lib.cooldown import Cooldown, CooldownBiTrigger
from services.lib.date_utils import HOUR
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.loans import AlertLendingOpenUpdate, LendingStats, PoolLendState


class LendingCapsNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

        self.cd_switch = self.deps.cfg.as_interval('lending.caps_alert.cooldown', 4 * HOUR)
        self.threshold = self.deps.cfg.as_float('lending.caps_alert.threshold', 99) / 100.0
        if self.threshold < 0.01:
            self.logger.warning(f'Caps alert threshold is too low: {self.threshold} ({self.threshold * 100}%)')
            self.threshold = 0.90
            self.logger.warning(f'Set to default: {self.threshold} ({self.threshold * 100}%)')

    async def _notify(self, event: LendingStats, pool_name: str):
        await self.pass_data_to_listeners(AlertLendingOpenUpdate(pool_name, event))

    async def _handle_pool(self, pool_name: str, pool: PoolLendState, event: LendingStats):
        cd_is_open = CooldownBiTrigger(self.deps.db, f'Lending:Open:Switch:{pool_name}',
                                       switch_cooldown_sec=self.cd_switch,
                                       default=True)

        r = await self.deps.db.get_redis()

        if pool.fill_ratio > 1.0:
            self.logger.info(f'Pool {pool_name} has fill ratio > 1.0: {pool.fill_ratio:.2f}')
            await cd_is_open.turn(on=False)
        elif pool.fill_ratio < self.threshold:
            self.logger.info(f'Pool {pool_name} has fill ratio < threshold: '
                             f'{pool.fill_ratio:.2f} < {self.threshold:.2f}')
            if await cd_is_open.turn(on=True):
                await self._notify(event, pool_name)

    async def on_data(self, sender, event: LendingStats):
        for lend_pool in event.pools:
            await self._handle_pool(lend_pool.collateral_name, lend_pool, event)
