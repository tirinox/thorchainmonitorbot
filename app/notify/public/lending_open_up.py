from lib.cooldown import CooldownBiTrigger, Cooldown
from lib.date_utils import HOUR
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.utils import WithLogger
from models.loans import AlertLendingOpenUpdate, LendingStats, BorrowerPool


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
        cd = Cooldown(self.deps.db, f'Lending:Open:{pool_name}', self.cd_switch)
        if await cd.can_do():
            self.logger.info(f'Caps alert for pool {pool_name})')
            await self.pass_data_to_listeners(AlertLendingOpenUpdate(pool_name, event))
            await cd.do()

    @staticmethod
    def _key(pool_name: str):
        return f'Lending:Open:{pool_name}'

    async def _handle_pool(self, pool_name: str, pool: BorrowerPool, event: LendingStats):
        r = await self.deps.db.get_redis()
        previous_above_caps = await r.hget(self._key(pool_name), 'above_caps')
        previous_above_caps = int(previous_above_caps) if previous_above_caps is not None else 0

        # print(f'Pool {pool_name} is above caps: {pool.fill_ratio:.2f}. {previous_above_caps =}')

        # hysteresis logic
        if previous_above_caps and pool.fill < self.threshold:
            await r.hset(self._key(pool_name), mapping={'above_caps': 0})
            await self._notify(event, pool_name)

        if not previous_above_caps and pool.fill >= 1.0:
            await r.hset(self._key(pool_name), mapping={'above_caps': 1})
            self.logger.info(f'Pool {pool_name} is above caps: {pool.fill:.2f}')

    async def on_data(self, sender, event: LendingStats):
        for lend_pool in event.pools:
            await self._handle_pool(lend_pool.pool, lend_pool, event)
