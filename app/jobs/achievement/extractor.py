from collections import defaultdict
from typing import List

from jobs.fetch.account_number import AccountNumberFetcher
from lib.constants import THORCHAIN_BIRTHDAY
from lib.date_utils import full_years_old_ts
from lib.depcont import DepContainer
from lib.logs import WithLogger
from lib.utils import is_list_of_type
from models.key_stats_model import AlertKeyStats
from models.memo import ActionType
from models.mimir import MimirTuple
from models.net_stats import NetworkStats
from models.node_info import NodeSetChanges
from models.price import RuneMarketInfo
from models.runepool import AlertPOLState, AlertRunePoolAction
from models.trade_acc import AlertTradeAccountStats, AlertTradeAccountAction
from models.tx import ThorAction
from .ach_list import A, EventTestAchievement, Achievement
from ..fetch.cached.last_block import EventLastBlock


class AchievementsExtractor(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    async def extract_events_by_type(self, sender, data) -> List[Achievement]:
        if isinstance(data, NetworkStats):
            kv_events = self.on_network_stats(data)
        # fixme
        elif isinstance(sender, EventLastBlock):
            kv_events = self.on_block(sender)  # sender not data!
        elif isinstance(data, NodeSetChanges):
            kv_events = self.on_node_changes(data)
        elif isinstance(data, MimirTuple):
            kv_events = self.on_mimir(data)
        elif isinstance(data, RuneMarketInfo):
            kv_events = self.on_rune_market_info(data)
        elif isinstance(sender, AccountNumberFetcher):
            kv_events = [Achievement(A.WALLET_COUNT, int(data))]
        elif is_list_of_type(data, ThorAction):
            usd_per_rune = await self.deps.pool_cache.get_usd_per_rune()
            kv_events = self.on_thor_tx_list(data, usd_per_rune)
        elif isinstance(data, AlertPOLState):
            kv_events = self.on_thor_pol(data)
            kv_events += self.on_runepool_stats(data)
        elif isinstance(data, AlertKeyStats):
            kv_events = self.on_weekly_stats(data)
        elif isinstance(data, EventTestAchievement):
            kv_events = self.on_test_event(data)
        elif isinstance(data, AlertTradeAccountStats):
            kv_events = self.on_trade_asset_summary(data)
        elif isinstance(data, AlertTradeAccountAction):
            kv_events = self.on_trade_asset_action(data)

        # todo: add event types for Trade accounts!

        else:
            self.logger.warning(f'Unknown data type {type(data)} from {sender}. Dont know how to handle it.')
            kv_events = []
        return kv_events

    @staticmethod
    def on_test_event(data: EventTestAchievement):
        if data.specialization:
            return [Achievement(A.TEST_SPEC, data.value, specialization=data.specialization)]
        elif data.descending:
            return [Achievement(A.TEST_DESCENDING, data.value, descending=True)]
        else:
            return [Achievement(A.TEST, data.value)]

    @staticmethod
    def on_network_stats(data: NetworkStats):
        events = [
            Achievement(A.DAU, data.users_daily),
            Achievement(A.MAU, data.users_monthly),
            Achievement(A.SWAP_COUNT_TOTAL, data.swaps_total),
            Achievement(A.SWAP_COUNT_24H, data.swaps_24h),
            Achievement(A.SWAP_COUNT_30D, data.swaps_30d),
            Achievement(A.ADD_LIQUIDITY_COUNT_TOTAL, data.add_count),
            Achievement(A.ADD_LIQUIDITY_VOLUME_TOTAL, int(data.added_rune)),

            Achievement(A.TOTAL_ACTIVE_BOND, int(data.total_active_bond_rune)),
            Achievement(A.TOTAL_BOND, int(data.total_bond_rune)),

            Achievement(A.SWAP_VOLUME_TOTAL_RUNE, int(data.swap_volume_rune)),
        ]
        return events

    @staticmethod
    def on_block(block_ev: EventLastBlock):
        years_old = full_years_old_ts(THORCHAIN_BIRTHDAY)

        achievements = [
            Achievement(A.BLOCK_NUMBER, block_ev.thor_block),
            Achievement(A.ANNIVERSARY, years_old),
        ]
        return achievements

    @staticmethod
    def on_node_changes(data: NodeSetChanges):
        events = [
            Achievement(A.NODE_COUNT, len(data.nodes_all)),
            Achievement(A.ACTIVE_NODE_COUNT, len(data.active_only_nodes)),
            # todo: total countries
        ]
        return events

    @staticmethod
    def on_mimir(data: MimirTuple):
        achievements = [
            Achievement(A.TOTAL_MIMIR_VOTES, len(data.votes)),
        ]
        return achievements

    @staticmethod
    def on_rune_market_info(data: RuneMarketInfo):
        events = [
            Achievement(A.MARKET_CAP_USD, data.market_cap),
            Achievement(A.TOTAL_POOLS, data.total_pools),
            Achievement(A.TOTAL_ACTIVE_POOLS, data.total_active_pools),
            Achievement(A.COIN_MARKET_CAP_RANK, data.rank, descending=True) if data.rank else None,
        ]
        return events

    @staticmethod
    def on_thor_tx_list(txs: List[ThorAction], usd_per_rune):
        results = defaultdict(float)

        def update(key, value, spec=''):
            results[(key, spec)] = max(results[(key, spec)], value)

        price = usd_per_rune or 0.0

        for tx in txs:
            this_volume = tx.get_usd_volume(price)
            if tx.is_of_type(ActionType.SWAP):
                update(A.MAX_SWAP_AMOUNT_USD, this_volume)
            elif tx.is_of_type(ActionType.ADD_LIQUIDITY):
                update(A.MAX_ADD_AMOUNT_USD, this_volume)

        return [
            Achievement(key, int(value), specialization=spec) for (key, spec), value in results.items()
        ]

    @staticmethod
    def on_thor_pol(pol: AlertPOLState):
        return [
            Achievement(A.POL_VALUE_RUNE, int(pol.current.rune_value))
        ]

    @staticmethod
    def on_weekly_stats(ev: AlertKeyStats):
        total_locked, _ = ev.locked_value_usd_curr_prev
        weekly_protocol_revenue = ev.current.earnings.total_earnings
        weekly_affiliate_revenue = ev.current.earnings.affiliate_revenue
        weekly_swap_volume, _ = ev.usd_volume_curr_prev
        total_locked_value_usd = total_locked.total_value_locked_usd

        results = [
            Achievement(A.BTC_IN_VAULT, int(ev.get_btc())),
            Achievement(A.ETH_IN_VAULT, int(ev.get_eth())),
            Achievement(A.STABLES_IN_VAULT, int(ev.get_stables_sum())),

            Achievement(A.TOTAL_VALUE_LOCKED, int(total_locked_value_usd)),
            Achievement(A.WEEKLY_PROTOCOL_REVENUE_USD, int(weekly_protocol_revenue)),
            Achievement(A.WEEKLY_AFFILIATE_REVENUE_USD, int(weekly_affiliate_revenue)),
            Achievement(A.WEEKLY_SWAP_VOLUME, int(weekly_swap_volume))
        ]
        return results

    @staticmethod
    def on_trade_asset_summary(data: AlertTradeAccountStats):
        return [
            Achievement(A.TRADE_ASSET_HOLDERS_COUNT, data.curr.vaults.total_traders),
            Achievement(A.TRADE_BALANCE_TOTAL_USD, int(data.curr.vaults.total_usd)),

            # todo more
            # Achievement(A.TRADE_ASSET_SWAPS_VOLUME, int()),
            # Achievement(A.TRADE_ASSET_SWAPS_COUNT, int()),
            # Achievement(A.TRADE_ASSET_MOVE_COUNT, int(),
        ]

    @staticmethod
    def on_trade_asset_action(data: AlertTradeAccountAction):
        # todo
        if data.is_deposit:
            return [
                Achievement(A.TRADE_ASSET_LARGEST_DEPOSIT, int(data.usd_amount))
            ]
        else:
            return []

    @staticmethod
    def on_runepool_action(data: AlertRunePoolAction):
        return [
            Achievement(A.RUNEPOOL_LARGEST_DEPOSIT, int(data.usd_amount))
        ]

    @staticmethod
    def on_runepool_stats(data: AlertPOLState):
        return [
            Achievement(A.RUNEPOOL_PNL, data.runepool.pnl),
            Achievement(A.RUNEPOOL_TOTAL_PROVIDERS, data.runepool.n_providers),
            Achievement(A.RUNEPOOL_VALUE_USD, data.runepool.usd_value),
        ]
