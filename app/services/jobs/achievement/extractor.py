from collections import defaultdict
from typing import List

from services.jobs.achievement.ach_list import A, EventTestAchievement, Achievement
from services.jobs.fetch.account_number import AccountNumberFetcher
from services.jobs.fetch.const_mimir import MimirTuple
from services.lib.constants import THORCHAIN_BIRTHDAY
from services.lib.date_utils import full_years_old_ts
from services.lib.depcont import DepContainer
from services.lib.utils import is_list_of_type, WithLogger
from services.models.asset import Asset
from services.models.flipside import AlertKeyStats
from services.models.loans import LendingStats, AlertLoanOpen
from services.models.memo import ActionType
from services.models.net_stats import NetworkStats
from services.models.node_info import NodeSetChanges
from services.models.runepool import AlertPOLState, AlertRunePoolAction
from services.models.price import RuneMarketInfo, LastPriceHolder
from services.models.savers import SaversBank
from services.models.trade_acc import AlertTradeAccountStats, AlertTradeAccountAction
from services.models.tx import ThorTx
from services.notify.types.block_notify import LastBlockStore


class AchievementsExtractor(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

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
        elif isinstance(data, SaversBank):
            kv_events = self.on_savers(data, self.deps.price_holder)
        elif isinstance(sender, AccountNumberFetcher):
            kv_events = [Achievement(A.WALLET_COUNT, int(data))]
        elif is_list_of_type(data, ThorTx):
            kv_events = self.on_thor_tx_list(data)
        elif isinstance(data, AlertPOLState):
            kv_events = self.on_thor_pol(data)
            kv_events += self.on_runepool_stats(data)
        elif isinstance(data, AlertKeyStats):
            kv_events = self.on_weekly_stats(data)
        elif isinstance(data, EventTestAchievement):
            kv_events = self.on_test_event(data)
        elif isinstance(data, LendingStats):
            kv_events = self.on_lending_stats(data)
        elif isinstance(data, AlertLoanOpen):
            kv_events = self.on_loan_open(data)
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
    def on_block(sender: LastBlockStore):
        years_old = full_years_old_ts(THORCHAIN_BIRTHDAY)

        achievements = [
            Achievement(A.BLOCK_NUMBER, int(sender.last_thor_block)),
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
            Achievement(A.RUNE_BURNT_LENDING, int(data.supply_info.lending_burnt_rune)),
        ]
        return events

    @staticmethod
    def on_savers(data: SaversBank, price_holder: LastPriceHolder):
        rune_price = price_holder.usd_per_rune or 0.0
        events = [
            Achievement(A.TOTAL_UNIQUE_SAVERS, data.total_unique_savers),
            Achievement(A.TOTAL_SAVED_USD, int(data.total_usd_saved)),
            Achievement(A.TOTAL_SAVERS_EARNED_USD, data.total_rune_earned * rune_price),
        ]
        for vault in data.vaults:
            asset = Asset.from_string(vault.asset).name[:10]
            events.append(Achievement(A.SAVER_VAULT_MEMBERS, vault.number_of_savers, specialization=asset))
            events.append(Achievement(A.SAVER_VAULT_SAVED_USD, int(vault.total_asset_saved_usd), specialization=asset))
            if not 'USD' in asset:
                events.append(
                    Achievement(A.SAVER_VAULT_SAVED_ASSET, int(vault.total_asset_saved), specialization=asset))

            earned = vault.calc_asset_earned(price_holder.pool_info_map)
            events.append(Achievement(A.SAVER_VAULT_EARNED_ASSET, int(earned), specialization=asset))

        return events

    def on_thor_tx_list(self, txs: List[ThorTx]):
        results = defaultdict(float)

        def update(key, value, spec=''):
            results[(key, spec)] = max(results[(key, spec)], value)

        price = self.deps.price_holder.usd_per_rune or 0.0

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
        weekly_protocol_revenue, _ = ev.total_revenue_usd_curr_prev
        weekly_affiliate_revenue, _ = ev.affiliate_fee_usd_curr_prev
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
    def on_lending_stats(data: LendingStats):
        return [
            Achievement(A.BORROWER_COUNT, data.borrower_count),
            Achievement(A.LOANS_OPENED, data.lending_tx_count),
            Achievement(A.TOTAL_COLLATERAL_USD, int(data.total_collateral_value_usd)),
            Achievement(A.TOTAL_BORROWED_USD, int(data.total_borrowed_amount_usd)),
        ]

    @staticmethod
    def on_loan_open(data: AlertLoanOpen):
        return [
            Achievement(A.MAX_LOAN_AMOUNT_USD, int(data.loan.debt_issued)),
        ]

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
