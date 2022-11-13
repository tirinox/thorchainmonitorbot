from typing import List

from services.lib.config import SubConfig
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.money import Asset, DepthCurve
from services.lib.utils import class_logger
from services.models.tx import ThorTx, EventLargeTransaction, ThorTxType
from services.notify.types.cap_notify import LiquidityCapNotifier


class GenericTxNotifier(INotified, WithDelegates):
    def __init__(self, deps: DepContainer, params: SubConfig, tx_types, curve: DepthCurve):
        super().__init__()
        self.deps = deps
        self.params = params
        self.tx_types = tx_types
        self.logger = class_logger(self)
        self.max_tx_per_single_message = deps.cfg.as_int('tx.max_tx_per_single_message', 5)

        self.curve = curve
        self.curve_mult = params.as_float('curve_mult', 1.0)

        self.max_age_sec = parse_timespan_to_seconds(deps.cfg.tx.max_age)
        self.min_usd_total = int(params.min_usd_total)

    async def on_data(self, senders, txs: List[ThorTx]):
        txs = [tx for tx in txs if tx.type in self.tx_types]  # filter my TX types
        if not txs:
            return

        usd_per_rune = self.deps.price_holder.usd_per_rune
        if not usd_per_rune:
            self.logger.error(f'Can not filter Txs, no USD/Rune price')
            return

        min_rune_volume = self.min_usd_total / usd_per_rune

        large_txs = [tx for tx in txs if self.is_tx_suitable(tx, min_rune_volume, usd_per_rune)]
        large_txs = large_txs[:self.max_tx_per_single_message]  # limit for 1 notification

        if not large_txs:
            return

        self.logger.info(f"Large Txs count is {len(large_txs)}.")

        cap_info = await LiquidityCapNotifier.get_last_cap_from_db(self.deps.db)
        has_liquidity = any(tx.is_liquidity_type for tx in large_txs)

        for tx in large_txs:
            is_last = tx == large_txs[-1]
            pool_info = self.deps.price_holder.pool_info_map.get(tx.first_pool)
            await self.pass_data_to_listeners(EventLargeTransaction(
                tx, usd_per_rune,
                pool_info,
                cap_info=(cap_info if has_liquidity and is_last else None)
            ))

    def _get_min_usd_depth(self, tx: ThorTx, usd_per_rune):
        pools = tx.pools
        if not pools:
            # in case of refund maybe
            pools = [Asset.convert_synth_to_pool_name(tx.first_input_tx.first_asset)]

        pool_info_list = list(filter(bool, (self.deps.price_holder.pool_info_map.get(pool) for pool in pools)))
        if not pool_info_list:
            return 0.0
        min_pool_depth = min(p.usd_depth(usd_per_rune) for p in pool_info_list)
        return min_pool_depth

    def is_tx_suitable(self, tx: ThorTx, min_rune_volume, usd_per_rune):
        pool_usd_depth = self._get_min_usd_depth(tx, usd_per_rune)
        if pool_usd_depth == 0.0:
            self.logger.warning(f'No pool depth for Tx: {tx}.')
            min_share_rune_volume = 0.0
        else:
            min_pool_share = self.curve.evaluate(pool_usd_depth) * self.curve_mult
            min_share_rune_volume = pool_usd_depth / usd_per_rune * min_pool_share

        if tx.full_rune >= min_rune_volume and tx.full_rune >= min_share_rune_volume:
            return True


class SwitchTxNotifier(GenericTxNotifier):
    def calculate_killed_rune(self, in_rune: float, block: int):
        survive_rate = 1.0 - self.deps.mimir_const_holder.current_old_rune_kill_progress(block)
        return in_rune * survive_rate

    def _count_correct_output_rune_value(self, tx: ThorTx):
        tx.rune_amount = self.calculate_killed_rune(tx.asset_amount, tx.height_int)
        return tx

    def is_tx_suitable(self, tx: ThorTx, min_rune_volume, usd_per_rune):
        if tx.asset_amount >= min_rune_volume:
            self._count_correct_output_rune_value(tx)
            return True


class LiquidityTxNotifier(GenericTxNotifier):
    def __init__(self, deps: DepContainer, params: SubConfig, curve: DepthCurve):
        super().__init__(deps, params, (ThorTxType.TYPE_WITHDRAW, ThorTxType.TYPE_ADD_LIQUIDITY), curve)
        self.ilp_paid_min_usd = params.as_float('also_trigger_when.ilp_paid_min_usd', 6000)

    def is_tx_suitable(self, tx: ThorTx, min_rune_volume, usd_per_rune):
        if tx.meta_withdraw and (tx.meta_withdraw.ilp_rune >= self.ilp_paid_min_usd / usd_per_rune):
            return True

        return super().is_tx_suitable(tx, min_rune_volume, usd_per_rune)


class SwapTxNotifier(GenericTxNotifier):
    def __init__(self, deps: DepContainer, params: SubConfig, curve: DepthCurve):
        super().__init__(deps, params, (ThorTxType.TYPE_SWAP,), curve)
        self.dex_min_usd = params.as_float('also_trigger_when.dex_aggregator_used.min_usd_total', 500)
        self.aff_fee_min_usd = params.as_float('also_trigger_when.affiliate_fee_usd_greater', 500)

    def is_tx_suitable(self, tx: ThorTx, min_rune_volume, usd_per_rune):
        affiliate_fee_rune = tx.meta_swap.affiliate_fee * tx.full_rune

        if affiliate_fee_rune >= self.aff_fee_min_usd / usd_per_rune:
            return True

        if tx.dex_aggregator_used and tx.full_rune >= self.dex_min_usd / usd_per_rune:
            return True

        return super().is_tx_suitable(tx, min_rune_volume, usd_per_rune)
