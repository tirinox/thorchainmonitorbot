import json
import math
from typing import NamedTuple, Optional

from services.jobs.fetch.const_mimir import MimirTuple
from services.lib.date_utils import now_ts, YEAR
from services.lib.db import DB
from services.lib.delegates import WithDelegates, INotified
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.net_stats import NetworkStats
from services.models.node_info import NodeSetChanges
from services.models.price import RuneMarketInfo
from services.notify.types.block_notify import LastBlockStore

THORCHAIN_BIRTHDAY = 1618058210955  # 2021-04-10T12:36:50.955991742Z


class Achievement:
    TEST = '__test'

    DAU = 'dau'
    MAU = 'mau'
    WALLET_COUNT = 'wallet_count'  # todo

    DAILY_TX_COUNT = 'daily_tx_count'  # todo
    DAILY_VOLUME = 'daily_volume'  # todo
    BLOCK_NUMBER = 'block_number'
    ANNIVERSARY = 'anniversary'

    SWAP_COUNT_TOTAL = 'swap_count_total'
    SWAP_COUNT_24H = 'swap_count_24h'
    SWAP_COUNT_30D = 'swap_count_30d'
    SWAP_UNIQUE_COUNT = 'swap_unique_count'

    ADD_LIQUIDITY_COUNT_TOTAL = 'add_liquidity_count_total'
    ADD_LIQUIDITY_VOLUME_TOTAL = 'add_liquidity_volume_total'

    ILP_PAID_TOTAL = 'ilp_paid_total'

    NODE_COUNT = 'node_count'
    ACTIVE_NODE_COUNT = 'active_node_count'
    TOTAL_ACTIVE_BOND = 'total_active_bond'
    TOTAL_BOND = 'total_bond'
    CHURNED_IN_BOND = 'churned_in_bond'

    TOTAL_MIMIR_VOTES = 'total_mimir_votes'

    # every single digit is a milestone
    GROUP_EVERY_1 = {
        BLOCK_NUMBER,
        ANNIVERSARY,
    }

    # this metrics only trigger when greater than their minimums
    GROUP_MINIMALS = {
        DAU: 300,
        MAU: 6500,
        WALLET_COUNT: 61000,
        BLOCK_NUMBER: 7_000_000,
        ANNIVERSARY: 1,
    }

    @classmethod
    def all_keys(cls):
        return [getattr(cls, k) for k in cls.__dict__
                if not k.startswith('_') and not k.startswith('GROUP') and k.upper() == k]


class Milestones:
    MILESTONE_DEFAULT_PROGRESSION = [1, 2, 5]

    def __init__(self, progression=None):
        self.progression = progression or self.MILESTONE_DEFAULT_PROGRESSION

    def milestone_nearest(self, x, before: bool):
        progress = self.progression
        x = int(x)
        if x <= 0:
            return self.progression[0]

        mag = 10 ** int(math.log10(x))
        if before:
            delta = -1
            mag *= 10
        else:
            delta = 1
        i = 0

        while True:
            step = progress[i]
            y = step * mag
            if before and x >= y:
                return y
            if not before and x < y:
                return y
            i += delta
            if i < 0:
                i = len(progress) - 1
                mag //= 10
            elif i >= len(progress):
                i = 0
                mag *= 10

    def next(self, x):
        return self.milestone_nearest(x, before=False)

    def previous(self, x):
        return self.milestone_nearest(x, before=True)


class AchievementRecord(NamedTuple):
    key: str
    value: int  # real current value
    milestone: int  # current milestone
    timestamp: float
    prev_milestone: int
    previous_ts: float


class EventAchievement(NamedTuple):
    achievement: AchievementRecord


class AchievementsTracker(WithLogger):
    def __init__(self, db: DB):
        super().__init__()
        self.db = db
        self.milestones = Milestones()
        self.milestones_every = Milestones(list(range(1, 10)))

    def key(self, name):
        return f'Achievements:{name}'

    @staticmethod
    def get_minimum(key):
        return Achievement.GROUP_MINIMALS.get(key, 1)

    def get_previous_milestone(self, key, value):
        if key in Achievement.GROUP_EVERY_1:
            v = self.milestones_every.previous(value)
        else:
            v = self.milestones.previous(value)

        return v

    async def feed_data(self, name: str, value: int) -> Optional[EventAchievement]:
        assert name

        if value < self.get_minimum(name):
            return None

        record = await self.get_achievement_record(name)
        current_milestone = self.get_previous_milestone(name, value)
        if record is None:
            # first time, just write and return
            record = AchievementRecord(
                str(name), value, current_milestone, now_ts(), 0, 0
            )
            await self.set_achievement_record(record)
            self.logger.info(f'New achievement record created {record}')
        else:
            # check if we need to update
            if current_milestone > record.value:
                record = AchievementRecord(
                    str(name), value, current_milestone, now_ts(),
                    prev_milestone=record.milestone, previous_ts=record.timestamp
                )
                await self.set_achievement_record(record)
                self.logger.info(f'Achievement record updated {record}')
                return EventAchievement(record)

    async def get_achievement_record(self, key) -> Optional[AchievementRecord]:
        key = self.key(key)
        data = await self.db.redis.get(key)
        try:
            return AchievementRecord(**json.loads(data))
        except (TypeError, json.JSONDecodeError):
            return None

    async def set_achievement_record(self, record: AchievementRecord):
        key = self.key(record.key)
        await self.db.redis.set(key, json.dumps(record._asdict()))

    async def delete_achievement_record(self, key):
        key = self.key(key)
        await self.db.redis.delete(key)


class AchievementTest(NamedTuple):
    value: int


class AchievementsNotifier(WithLogger, WithDelegates, INotified):
    async def extract_events_by_type(self, sender, data):
        if isinstance(data, NetworkStats):
            kv_events = self.on_network_stats(data)
        elif isinstance(sender, LastBlockStore):
            kv_events = self.on_block(sender)  # sender not data!
        elif isinstance(data, NodeSetChanges):
            kv_events = self.on_node_changes(data)
        elif isinstance(data, MimirTuple):
            kv_events = self.on_mimir(data)
        elif isinstance(data, RuneMarketInfo):
            kv_events = self.on_rune_market_info(data)
        elif isinstance(data, AchievementTest):
            kv_events = [(Achievement.TEST, data.value)]
        else:
            self.logger.warning(f'Unknown data type {type(data)}. Dont know how to handle it.')
            kv_events = []
        return kv_events

    @staticmethod
    def on_network_stats(data: NetworkStats):
        achievements = [
            (Achievement.DAU, data.users_daily),
            (Achievement.MAU, data.users_monthly),
            (Achievement.SWAP_COUNT_TOTAL, data.swaps_total),
            (Achievement.SWAP_COUNT_24H, data.swaps_24h),
            (Achievement.SWAP_COUNT_30D, data.swaps_30d),
            (Achievement.SWAP_UNIQUE_COUNT, data.unique_swapper_count),
            (Achievement.ADD_LIQUIDITY_COUNT_TOTAL, data.add_count),
            (Achievement.ADD_LIQUIDITY_VOLUME_TOTAL, data.added_rune),
            (Achievement.ILP_PAID_TOTAL, data.loss_protection_paid_rune),

            (Achievement.TOTAL_ACTIVE_BOND, data.total_active_bond_rune),
            (Achievement.TOTAL_BOND, data.total_bond_rune),
        ]
        return achievements

    @staticmethod
    def on_block(sender: LastBlockStore):
        years_old = int((now_ts() - THORCHAIN_BIRTHDAY * 0.001) / YEAR)
        achievements = [
            (Achievement.BLOCK_NUMBER, int(sender.last_thor_block)),
            (Achievement.ANNIVERSARY, years_old),
        ]
        return achievements

    @staticmethod
    def on_node_changes(data: NodeSetChanges):
        achievements = [
            (Achievement.CHURNED_IN_BOND, data.bond_churn_in),
            (Achievement.NODE_COUNT, len(data.nodes_all)),
            (Achievement.ACTIVE_NODE_COUNT, len(data.active_only_nodes)),
        ]
        return achievements

    @staticmethod
    def on_mimir(data: MimirTuple):
        achievements = [
            # todo
            (Achievement.TOTAL_MIMIR_VOTES, len(data.votes)),
        ]
        return achievements

    @staticmethod
    def on_rune_market_info(data: RuneMarketInfo):
        achievements = [
            # todo 1) market cap 2) pool count 3) active pool count 4) rank (reversed)
        ]
        return achievements

    async def on_data(self, sender, data):
        try:
            kv_events = await self.extract_events_by_type(sender, data)

            for key, value in kv_events:
                event = await self.tracker.feed_data(key, value)
                if event:
                    self.logger.info(f'Achievement even occurred {event}!')
                    await self.pass_data_to_listeners(event)
        except Exception as e:
            # we don't let any exception in the Achievements module to break the whole system
            self.logger.exception(f'Error while processing data {type(data)} from {type(sender)}: {e}', exc_info=True)

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.tracker = AchievementsTracker(deps.db)
