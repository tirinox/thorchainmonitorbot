from jobs.scanner.native_scan import BlockResult
from lib.active_users import DailyActiveUserCounter, UserStats
from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger


class UserCounterMiddleware(INotified, WithLogger):
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

    def get_unique_users(self, data: BlockResult):
        users = set()
        for ev in data.end_block_events:
            for field in self.USER_FIELDS:
                value = ev.attrs.get(field)
                if value and value:
                    users.add(value)

        for tx in data.txs:
            for msg in tx.messages:
                if msg.type == msg.MsgObservedTxIn:
                    for observed_tx in msg.txs:
                        if observed_tx and observed_tx.get('tx'):
                            user = observed_tx['tx'].get('from_address')
                            if user:
                                users.add(user)

        users -= self._excluded_addresses
        return users

    async def on_data(self, sender, data: BlockResult):
        users = self.get_unique_users(data)
        if users:
            self.logger.info(f'Adding {len(users)} unique users at this tick.')
            self.logger.debug(f'{users = }')
        await self._counter.hit(users=users)

        # Example of usage:
        # ---------------------------------------------
        # dau = await self._counter.get_dau()
        # wau = await self._counter.get_wau()
        # mau = await self._counter.get_mau()
        # print(f'{dau = }, {wau = }, {mau = }')
        # ---------------------------------------------

    async def get_main_stats(self) -> UserStats:
        self._counter.r = self.deps.db.redis
        return await self._counter.get_stats()

    @property
    def counter(self) -> DailyActiveUserCounter:
        return self._counter
