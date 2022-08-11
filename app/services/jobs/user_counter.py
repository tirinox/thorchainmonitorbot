from services.jobs.fetch.native_scan import BlockResult
from services.lib.active_users import DailyActiveUserCounter, UserStats
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger


class UserCounter(INotified, WithLogger):
    def __init__(self, d: DepContainer):
        super().__init__()
        self.deps = d
        self._counter = DailyActiveUserCounter(d.db.redis, 'Main')
        self._excluded_addresses = set(
            d.cfg.get_pure('native_scanner.user_counting.exclude_addresses', [])
        )

    USER_FIELDS = [
        'from', 'to', 'sender', 'recipient'
    ]

    async def on_data(self, sender, data: BlockResult):
        users = set()
        for ev in data.end_block_events:
            for field in self.USER_FIELDS:
                value = ev.attributes.get(field)
                if value and value:
                    users.add(value)

        users -= self._excluded_addresses
        self.logger.info(f'Adding {len(users)} unique users at this tick.')

        await self._counter.hit(users=users)

        # Example of usage:
        # ---------------------------------------------
        # dau = await self._counter.get_dau()
        # wau = await self._counter.get_wau()
        # mau = await self._counter.get_mau()
        # print(f'{dau = }, {wau = }, {mau = }')
        # ---------------------------------------------

    async def get_main_stats(self) -> UserStats:
        return await self._counter.get_stats()
