from collections import defaultdict
from typing import List

from services.jobs.achievement.ach_list import A, AchievementTest
from services.jobs.fetch.account_number import AccountNumberFetcher
from services.jobs.fetch.const_mimir import MimirTuple
from services.lib.constants import THORCHAIN_BIRTHDAY
from services.lib.date_utils import full_years_old_ts
from services.lib.depcont import DepContainer
from services.lib.money import Asset
from services.lib.utils import is_list_of_type, WithLogger
from services.models.net_stats import NetworkStats
from services.models.node_info import NodeSetChanges
from services.models.price import RuneMarketInfo, LastPriceHolder
from services.models.savers import AllSavers
from services.models.tx import ThorTx, ThorTxType
from services.notify.types.block_notify import LastBlockStore


class AchievementsExtractor(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    async def extract_events_by_type(self, sender, data) -> List[A]:
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
        elif is_list_of_type(data, ThorTx):
            kv_events = self.on_thor_tx_list(data)
        elif isinstance(data, AchievementTest):
            kv_events = self.on_test_event(data)
        else:
            self.logger.warning(f'Unknown data type {type(data)} from {sender}. Dont know how to handle it.')
            kv_events = []
        return kv_events

    @staticmethod
    def on_test_event(data: AchievementTest):
        if data.specialization:
            return [A(A.TEST_SPEC, data.value, specialization=data.specialization)]
        elif data.descending:
            return [A(A.TEST_DESCENDING, data.value, descending=True)]
        else:
            return [A(A.TEST, data.value)]

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

    def on_thor_tx_list(self, txs: List[ThorTx]):
        results = defaultdict(float)

        def update(key, value, spec=''):
            results[(key, spec)] = max(results[(key, spec)], value)

        price = self.deps.price_holder.usd_per_rune or 0.0

        for tx in txs:
            this_volume = tx.get_usd_volume(price)
            if tx.type == ThorTxType.TYPE_SWAP:
                update(A.MAX_SWAP_AMOUNT_USD, this_volume)
            elif tx.type == ThorTxType.TYPE_ADD_LIQUIDITY:
                update(A.MAX_ADD_AMOUNT_USD, this_volume)

        return [
            A(key, int(value), specialization=spec) for (key, spec), value in results.items()
        ]
