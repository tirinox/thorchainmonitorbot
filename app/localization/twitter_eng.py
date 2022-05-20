from typing import List

from aiothornode.types import ThorChainInfo
from semver import VersionInfo

from localization.base import BaseLocalization
from services.models.bep2 import BEP2CEXFlow, BEP2Transfer
from services.models.cap_info import ThorCapInfo
from services.models.last_block import EventBlockSpeed
from services.models.mimir import MimirChange, MimirHolder, MimirVoting, MimirVoteOption
from services.models.net_stats import NetworkStats
from services.models.node_info import NodeSetChanges, NodeVersionConsensus
from services.models.pool_info import PoolDetailHolder, PoolChanges, PoolInfo
from services.models.price import RuneMarketInfo, PriceReport
from services.models.tx import ThorTxExtended


class TwitterEnglishLocalization(BaseLocalization):
    def notification_text_cap_change(self, old: ThorCapInfo, new: ThorCapInfo):
        return ''  # todo!

    def notification_text_cap_opened_up(self, cap: ThorCapInfo):
        return ''  # todo!

    def notification_text_large_tx(self, tx: ThorTxExtended, usd_per_rune: float, pool_info: PoolInfo,
                                   cap: ThorCapInfo = None):
        return ''  # todo!

    def notification_text_queue_update(self, item_type, step, value):
        return ''  # todo!

    def notification_text_price_update(self, p: PriceReport, ath=False, halted_chains=None):
        return ''  # todo!

    def notification_text_price_divergence(self, info: RuneMarketInfo, normal: bool):
        return ''  # todo!

    def notification_text_pool_churn(self, pc: PoolChanges):
        return ''  # todo!

    def notification_text_network_summary(self, old: NetworkStats, new: NetworkStats, market: RuneMarketInfo):
        return ''  # todo!

    def notification_text_for_node_churn(self, changes: NodeSetChanges):
        return ''  # todo!

    def notification_text_version_upgrade_progress(self, data: NodeSetChanges, ver_con: NodeVersionConsensus):
        return ''  # todo!

    def notification_text_version_upgrade(self, data: NodeSetChanges, new_versions: List[VersionInfo],
                                          old_active_ver: VersionInfo, new_active_ver: VersionInfo):
        return ''  # todo!

    def notification_text_mimir_voting_progress(self, holder: MimirHolder, key, prev_progress, voting: MimirVoting,
                                                option: MimirVoteOption):
        return ''  # todo!

    def notification_text_trading_halted_multi(self, chain_infos: List[ThorChainInfo]):
        return ''  # todo!

    def notification_text_block_stuck(self, e: EventBlockSpeed):
        return ''  # todo!

    def notification_text_block_pace(self, e: EventBlockSpeed):
        return ''  # todo!

    def notification_text_mimir_changed(self, changes: List[MimirChange], mimir: MimirHolder):
        return ''  # todo!

    def notification_text_best_pools(self, pd: PoolDetailHolder, n_pools):
        return ''  # todo!

    def notification_text_bep2_movement(self, transfer: BEP2Transfer):
        return ''  # todo!

    def notification_text_cex_flow(self, bep2flow: BEP2CEXFlow):
        return ''  # todo!
