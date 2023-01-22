import json
import math
from typing import NamedTuple, Optional, List

from services.jobs.fetch.account_number import AccountNumberFetcher
from services.jobs.fetch.const_mimir import MimirTuple
from services.lib.cooldown import Cooldown
from services.lib.date_utils import now_ts, full_years_old_ts
from services.lib.db import DB
from services.lib.delegates import WithDelegates, INotified
from services.lib.depcont import DepContainer
from services.lib.money import Asset
from services.lib.utils import WithLogger
from services.models.net_stats import NetworkStats
from services.models.node_info import NodeSetChanges
from services.models.price import RuneMarketInfo, LastPriceHolder
from services.models.savers import AllSavers
from services.notify.types.block_notify import LastBlockStore

THORCHAIN_BIRTHDAY = 1618058210955 * 0.001  # 2021-04-10T12:36:50.955991742Z


class Achievement(NamedTuple):
    key: str
    value: int  # real current value
    milestone: int = 0  # current milestone
    timestamp: float = 0
    prev_milestone: int = 0
    previous_ts: float = 0
    specialization: str = ''

    TEST = '__test'
    TEST_SPEC = '__test_sp'

    DAU = 'dau'
    MAU = 'mau'
    WALLET_COUNT = 'wallet_count'

    DAILY_TX_COUNT = 'daily_tx_count'  # todo
    DAILY_VOLUME = 'daily_volume'  # todo
    BLOCK_NUMBER = 'block_number'
    ANNIVERSARY = 'anniversary'

    SWAP_COUNT_TOTAL = 'swap_count_total'
    SWAP_COUNT_24H = 'swap_count_24h'
    SWAP_COUNT_30D = 'swap_count_30d'
    SWAP_UNIQUE_COUNT = 'swap_unique_count'
    SWAP_VOLUME_TOTAL_RUNE = 'swap_volume_total_rune'

    ADD_LIQUIDITY_COUNT_TOTAL = 'add_liquidity_count_total'
    ADD_LIQUIDITY_VOLUME_TOTAL = 'add_liquidity_volume_total'

    ILP_PAID_TOTAL = 'ilp_paid_total'

    NODE_COUNT = 'node_count'
    ACTIVE_NODE_COUNT = 'active_node_count'
    TOTAL_ACTIVE_BOND = 'total_active_bond'
    TOTAL_BOND = 'total_bond'

    TOTAL_MIMIR_VOTES = 'total_mimir_votes'

    MARKET_CAP_USD = 'market_cap_usd'
    TOTAL_POOLS = 'total_pools'
    TOTAL_ACTIVE_POOLS = 'total_active_pools'

    TOTAL_UNIQUE_SAVERS = 'total_unique_savers'
    TOTAL_SAVED_USD = 'total_saved_usd'
    TOTAL_SAVERS_EARNED_USD = 'total_savers_earned_usd'

    SAVER_VAULT_SAVED_USD = 'saver_vault_saved_usd'
    SAVER_VAULT_SAVED_ASSET = 'saver_vault_saved_asset'
    SAVER_VAULT_MEMBERS = 'saver_vault_members'
    SAVER_VAULT_EARNED_ASSET = 'saver_vault_earned_asset'

    @classmethod
    def all_keys(cls):
        return [getattr(cls, k) for k in cls.__dict__
                if not k.startswith('_') and k.upper() == k]

    @property
    def has_previous(self):
        return self.prev_milestone > 0 and self.previous_ts > 0


A = Achievement

# every single digit is a milestone
GROUP_EVERY_1 = {
    A.BLOCK_NUMBER,
    A.ANNIVERSARY,
    A.WALLET_COUNT,  # ok?
}

# this metrics only trigger when greater than their minimums
GROUP_MINIMALS = {
    A.DAU: 300,
    A.MAU: 6500,
    A.WALLET_COUNT: 61000,
    A.BLOCK_NUMBER: 7_000_000,
    A.ANNIVERSARY: 1,
}


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


class AchievementsTracker(WithLogger):
    def __init__(self, db: DB):
        super().__init__()
        self.db = db
        self.milestones = Milestones()
        self.milestones_every = Milestones(list(range(1, 10)))

    @staticmethod
    def key(name, specialization=''):
        if specialization:
            return f'Achievements:{name}:{specialization}'
        else:
            return f'Achievements:{name}'

    @staticmethod
    def get_minimum(key):
        return GROUP_MINIMALS.get(key, 1)

    def get_previous_milestone(self, key, value):
        if key in GROUP_EVERY_1:
            v = self.milestones_every.previous(value)
        else:
            v = self.milestones.previous(value)

        return v

    async def feed_data(self, event: Achievement) -> Optional[Achievement]:
        name, value = event.key, event.value
        assert name

        if value < self.get_minimum(name):
            return None

        record = await self.get_achievement_record(name, event.specialization)
        current_milestone = self.get_previous_milestone(name, value)
        if record is None:
            # first time, just write and return
            record = Achievement(
                str(name), int(value), current_milestone, now_ts(),
                specialization=event.specialization
            )
            await self.set_achievement_record(record)
            self.logger.info(f'New achievement record created {record}')
        else:
            # check if we need to update
            if current_milestone > record.value:
                record = Achievement(
                    str(name), int(value), current_milestone, now_ts(),
                    prev_milestone=record.milestone, previous_ts=record.timestamp,
                    specialization=event.specialization,
                )
                await self.set_achievement_record(record)
                self.logger.info(f'Achievement record updated {record}')
                return record

    async def get_achievement_record(self, key, specialization) -> Optional[Achievement]:
        key = self.key(key, specialization)
        data = await self.db.redis.get(key)
        try:
            return Achievement(**json.loads(data))
        except (TypeError, json.JSONDecodeError):
            return None

    async def set_achievement_record(self, record: Achievement):
        key = self.key(record.key, record.specialization)
        await self.db.redis.set(key, json.dumps(record._asdict()))

    async def delete_achievement_record(self, key, specialization=''):
        key = self.key(key, specialization)
        await self.db.redis.delete(key)


class AchievementTest(NamedTuple):
    value: int
    specialization: str = ''


class AchievementsNotifier(WithLogger, WithDelegates, INotified):
    async def extract_events_by_type(self, sender, data) -> List[Achievement]:
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
        elif isinstance(data, AllSavers):
            kv_events = self.on_savers(data, self.deps.price_holder)
        elif isinstance(sender, AccountNumberFetcher):
            kv_events = [A(A.WALLET_COUNT, int(data))]
        elif isinstance(data, AchievementTest):
            if data.specialization:
                kv_events = [A(A.TEST_SPEC, data.value, specialization=data.specialization)]
            else:
                kv_events = [A(A.TEST, data.value)]
        else:
            self.logger.warning(f'Unknown data type {type(data)}. Dont know how to handle it.')
            kv_events = []
        return kv_events

    @staticmethod
    def on_network_stats(data: NetworkStats):
        achievements = [
            A(A.DAU, data.users_daily),
            A(A.MAU, data.users_monthly),
            A(A.SWAP_COUNT_TOTAL, data.swaps_total),
            A(A.SWAP_COUNT_24H, data.swaps_24h),
            A(A.SWAP_COUNT_30D, data.swaps_30d),
            A(A.SWAP_UNIQUE_COUNT, data.unique_swapper_count),
            A(A.ADD_LIQUIDITY_COUNT_TOTAL, data.add_count),
            A(A.ADD_LIQUIDITY_VOLUME_TOTAL, int(data.added_rune)),
            A(A.ILP_PAID_TOTAL, int(data.loss_protection_paid_rune)),

            A(A.TOTAL_ACTIVE_BOND, int(data.total_active_bond_rune)),
            A(A.TOTAL_BOND, int(data.total_bond_rune)),

            A(A.SWAP_VOLUME_TOTAL_RUNE, int(data.swap_volume_rune)),
        ]
        return achievements

    @staticmethod
    def on_block(sender: LastBlockStore):
        years_old = full_years_old_ts(THORCHAIN_BIRTHDAY)
        achievements = [
            A(A.BLOCK_NUMBER, int(sender.last_thor_block)),
            A(A.ANNIVERSARY, years_old),
        ]
        return achievements

    @staticmethod
    def on_node_changes(data: NodeSetChanges):
        achievements = [
            A(A.NODE_COUNT, len(data.nodes_all)),
            A(A.ACTIVE_NODE_COUNT, len(data.active_only_nodes)),
            # todo: total countries
        ]
        return achievements

    @staticmethod
    def on_mimir(data: MimirTuple):
        achievements = [
            A(A.TOTAL_MIMIR_VOTES, len(data.votes)),
        ]
        return achievements

    @staticmethod
    def on_rune_market_info(data: RuneMarketInfo):
        achievements = [
            A(A.MARKET_CAP_USD, data.market_cap),
            A(A.TOTAL_POOLS, data.total_pools),
            A(A.TOTAL_ACTIVE_POOLS, data.total_active_pools),
            # todo  4) rank (reversed)
        ]
        return achievements

    @staticmethod
    def on_savers(data: AllSavers, price_holder: LastPriceHolder):
        rune_price = price_holder.usd_per_rune or 0.0
        achievements = [
            A(A.TOTAL_UNIQUE_SAVERS, data.total_unique_savers),
            A(A.TOTAL_SAVED_USD, int(data.total_usd_saved)),
            A(A.TOTAL_SAVERS_EARNED_USD, data.total_rune_earned * rune_price),
        ]
        for vault in data.vaults:
            asset = Asset.from_string(vault.asset).name[:10]
            achievements.append(A(A.SAVER_VAULT_MEMBERS, vault.number_of_savers, specialization=asset))
            achievements.append(A(A.SAVER_VAULT_SAVED_USD, int(vault.total_asset_saved_usd), specialization=asset))
            achievements.append(A(A.SAVER_VAULT_SAVED_ASSET, int(vault.total_asset_saved), specialization=asset))
            achievements.append(A(A.SAVER_VAULT_EARNED_ASSET,
                                  vault.calc_asset_earned(price_holder.pool_info_map), specialization=asset))

        return achievements

    async def on_data(self, sender, data):
        try:
            kv_events = await self.extract_events_by_type(sender, data)

            for event in kv_events:
                event = await self.tracker.feed_data(event)
                if event:
                    self.logger.info(f'Achievement even occurred {event}!')

                    if await self.cd.can_do():
                        await self.cd.do()
                        await self.pass_data_to_listeners(event)
                    else:
                        self.logger.warning(f'Cooldown is active. Skipping achievement event {event}')

        except Exception as e:
            # we don't let any exception in the Achievements module to break the whole system
            self.logger.exception(f'Error while processing data {type(data)} from {type(sender)}: {e}', exc_info=True)

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.tracker = AchievementsTracker(deps.db)

        cd = deps.cfg.as_interval('achievements.cooldown.period', '10m')
        max_times = deps.cfg.as_int('achievements.cooldown.hits_before_cd', 3)
        self.cd = Cooldown(self.deps.db, 'Achievements:Notification', cd, max_times)
