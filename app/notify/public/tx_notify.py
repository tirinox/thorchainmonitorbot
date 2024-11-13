from typing import List, Optional

from api.aionode.types import ThorSwapperClout
from jobs.scanner.event_db import EventDatabase
from lib.config import SubConfig
from lib.date_utils import parse_timespan_to_seconds, MINUTE
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.money import DepthCurve, pretty_dollar, short_dollar
from lib.utils import WithLogger
from models.asset import Asset
from models.memo import ActionType
from models.tx import ThorTx, EventLargeTransaction
from notify.dup_stop import TxDeduplicator, TxDeduplicatorSenderCooldown
from notify.public.cap_notify import LiquidityCapNotifier
from notify.public.s_swap_notify import DB_KEY_ANNOUNCED_SS_START

DB_KEY_TX_ANNOUNCED_HASHES = 'large-tx:announced-hashes'


class GenericTxNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer, params: SubConfig, tx_types, curve: DepthCurve):
        super().__init__()
        self.deps = deps
        self.params = params
        self.tx_types = tx_types
        self.max_tx_per_single_message = deps.cfg.as_int('tx.max_tx_per_single_message', 5)

        self.curve = curve
        self.curve_mult = params.as_float('curve_mult', 1.0)

        self.max_age_sec = parse_timespan_to_seconds(deps.cfg.tx.max_age)
        self.min_usd_total = int(params.min_usd_total)
        self.logger.info(f"Min USD total is {short_dollar(self.min_usd_total)}.")
        self.no_repeat_protection = True

        self.deduplicator = TxDeduplicator(deps.db, DB_KEY_TX_ANNOUNCED_HASHES)

    async def on_data(self, senders, txs: List[ThorTx]):
        try:
            await self.handle_txs_unsafe(senders, txs)
        except Exception as e:
            self.logger.exception(f"Failed! {e}")

    async def handle_txs_unsafe(self, senders, txs: List[ThorTx]):
        # 1. filter irrelevant tx types
        txs = [tx for tx in txs if tx.is_of_type(self.tx_types)]  # filter my TX types

        # 2. Throw away announced Txs in the past
        if self.no_repeat_protection:
            txs = await self.deduplicator.only_new_txs(txs)

        if not txs:
            return

        # 3. Select only large transactions
        usd_per_rune = self.deps.price_holder.usd_per_rune
        if not usd_per_rune:
            self.logger.error(f'Can not filter Txs, no USD/Rune price')
            return

        min_rune_volume = self.min_usd_total / usd_per_rune

        large_txs = [tx for tx in txs if self.is_tx_suitable(tx, min_rune_volume, usd_per_rune)]
        if not large_txs:
            return

        # 4. Limit Tx count per 1 tick (basically the number of transactions in each alert)
        large_txs = large_txs[:self.max_tx_per_single_message]

        # 5. Pass them down the pipeline
        self.logger.info(f"Large Txs count is {len(large_txs)}.")

        cap_info = await LiquidityCapNotifier.get_last_cap_from_db(self.deps.db)
        has_liquidity = any(tx.is_liquidity_type for tx in large_txs)

        for tx in large_txs:
            is_last = tx == large_txs[-1]
            pool_info = self.deps.price_holder.pool_info_map.get(tx.first_pool_l1)

            clout = await self._get_clout(tx.sender_address)

            event = EventLargeTransaction(
                tx, usd_per_rune,
                pool_info,
                cap_info=(cap_info if has_liquidity and is_last else None),
                mimir=self.deps.mimir_const_holder,
                clout=clout,
            )

            event = await self._event_transform(event)

            await self.pass_data_to_listeners(event)

            if self.no_repeat_protection:
                await self.deduplicator.mark_as_seen(tx.tx_hash)

    async def _event_transform(self, event: EventLargeTransaction) -> EventLargeTransaction:
        return event

    async def get_tx_from_midgard(self, tx_hash):
        try:
            mdg = self.deps.midgard_connector
            txs = await mdg.query_transactions(
                mdg.urlgen.url_for_tx(txid=tx_hash)
            )
            if not txs or not txs.txs:
                raise Exception('Failed to load Tx from Midgard!')
            first_tx = txs.first
            if not first_tx:
                raise Exception('No first Tx in the list!')

            return first_tx
        except Exception as e:
            self.logger.error(f'Failed to verify liquidity fee: {e}')

    async def _get_clout(self, address) -> Optional[ThorSwapperClout]:
        try:
            return await self.deps.thor_connector.query_swapper_clout(address)
        except Exception as e:
            self.logger.error(f'Error getting clout for {address}: {e}')
            return None

    def _get_min_usd_depth(self, tx: ThorTx, usd_per_rune):
        pools = tx.pools
        if not pools:
            # in case of refund maybe
            pools = [tx.first_input_tx.first_asset]

        pools = [Asset.to_L1_pool_name(p) for p in pools]

        pool_info_list = list(filter(bool, (self.deps.price_holder.pool_info_map.get(pool) for pool in pools)))
        if not pool_info_list:
            return 0.0
        min_pool_depth = min(p.usd_depth(usd_per_rune) for p in pool_info_list)
        return min_pool_depth

    def is_tx_suitable(self, tx: ThorTx, min_rune_volume, usd_per_rune, curve_mult=None):
        pool_usd_depth = self._get_min_usd_depth(tx, usd_per_rune)
        if pool_usd_depth == 0.0:
            if not tx.is_of_type(ActionType.REFUND):
                self.logger.warning(f'No pool depth for Tx: {tx}.')
            min_share_rune_volume = 0.0
        else:
            if self.curve:
                curve_mult = curve_mult or self.curve_mult
                min_pool_share = self.curve.evaluate(pool_usd_depth) * curve_mult
                min_share_rune_volume = pool_usd_depth / usd_per_rune * min_pool_share
            else:
                min_share_rune_volume = 0.0

        if tx.full_volume_in_rune >= min_rune_volume and tx.full_volume_in_rune >= min_share_rune_volume:
            return True

    def dbg_evaluate_curve_for_pools(self, max_pools=20):
        pools = sorted(self.deps.price_holder.pool_info_map.values(), key=lambda p: p.balance_rune, reverse=True)
        usd_per_rune = self.deps.price_holder.usd_per_rune

        summary = " --- Threshold curve evaluation ---\n"
        for pool in pools[:max_pools]:
            if pool.asset.startswith('THOR'):  # no virtuals
                continue
            depth_usd = pool.usd_depth(usd_per_rune)
            min_pool_share = self.curve.evaluate(depth_usd) * self.curve_mult
            min_share_usd_volume = depth_usd * min_pool_share
            summary += f"Pool: {pool.asset[:20]:<20} => Min Tx volume is {pretty_dollar(min_share_usd_volume)}\n"
        self.logger.info(summary)


class LiquidityTxNotifier(GenericTxNotifier):
    def __init__(self, deps: DepContainer, params: SubConfig, curve: DepthCurve):
        super().__init__(deps, params, (ActionType.WITHDRAW, ActionType.ADD_LIQUIDITY), curve)
        self.ilp_paid_min_usd = params.as_float('also_trigger_when.ilp_paid_min_usd', 6000)

        self.savers_enabled = params.get('savers.enabled', True)
        self.savers_min_usd_total = params.as_float('savers.min_usd_total', 10_000.0)
        self.savers_curve_mult = params.as_float('savers.curve_mult', 0.4)

    def is_tx_suitable(self, tx: ThorTx, min_rune_volume, usd_per_rune, curve_mult=None):
        if tx.meta_withdraw and (tx.meta_withdraw.ilp_rune >= self.ilp_paid_min_usd / usd_per_rune):
            return True

        if tx.is_savings:
            min_rune_volume_savers = self.savers_min_usd_total / usd_per_rune
            if super().is_tx_suitable(tx, min_rune_volume_savers, usd_per_rune, self.savers_curve_mult):
                return True

        return super().is_tx_suitable(tx, min_rune_volume, usd_per_rune, curve_mult)


class SwapTxNotifier(GenericTxNotifier):
    def __init__(self, deps: DepContainer, params: SubConfig, curve: DepthCurve):
        super().__init__(deps, params, (ActionType.SWAP,), curve)
        self.dex_min_usd = params.as_float('also_trigger_when.dex_aggregator_used.min_usd_total', 500)
        self.aff_fee_min_usd = params.as_float('also_trigger_when.affiliate_fee_usd_greater', 500)
        self.min_streaming_swap_usd = params.as_float('also_trigger_when.streaming_swap.volume_greater', 2500)
        self.min_trade_asset_swap_usd = params.as_float('also_trigger_when.trade_asset_swap.volume_greater', 100_000)
        self._ss_txs_started = []  # Fill it every tick before is_tx_suitable is called.
        self._ev_db = EventDatabase(deps.db)
        self.swap_start_deduplicator = TxDeduplicator(deps.db, DB_KEY_ANNOUNCED_SS_START)

    async def _check_if_they_announced_as_started(self, txs: List[ThorTx]):
        if not txs:
            return

        only_seen_ss_txs = await self.swap_start_deduplicator.only_seen_txs(txs)

        self._ss_txs_started = set(tx.tx_hash for tx in only_seen_ss_txs)
        if self._ss_txs_started:
            self.logger.info(f'These Txs were announced as started SS before: {self._ss_txs_started}')

    async def handle_txs_unsafe(self, senders, txs: List[ThorTx]):
        await self._check_if_they_announced_as_started(txs)

        return await super().handle_txs_unsafe(senders, txs)

    async def adjust_liquidity_fee_through_midgard(self, event: EventLargeTransaction):
        try:
            tx = await self.get_tx_from_midgard(event.transaction.tx_hash)

            if not tx.meta_swap:
                raise Exception('No meta_swap in the first Tx!')

            liquidity_fee = tx.meta_swap.liquidity_fee
            prev_fee = event.transaction.meta_swap.liquidity_fee
            if prev_fee != liquidity_fee:
                self.logger.warning(f'Fee changed for {tx.tx_hash}: {prev_fee} -> {liquidity_fee}')
                event.transaction.meta_swap.liquidity_fee = liquidity_fee

            swap_slip = tx.meta_swap.trade_slip
            prev_slip = event.transaction.meta_swap.trade_slip
            if prev_slip != swap_slip:
                self.logger.warning(f'Slip changed for {tx.tx_hash}: {prev_slip} -> {swap_slip}')
                event.transaction.meta_swap.trade_slip = swap_slip
        except Exception as e:
            self.logger.error(f'Failed to verify liquidity fee: {e}')
        finally:
            return event

    async def _event_transform(self, event: EventLargeTransaction) -> EventLargeTransaction:
        return await self.adjust_liquidity_fee_through_midgard(event)

    def is_tx_suitable(self, tx: ThorTx, min_rune_volume, usd_per_rune, curve_mult=None):
        # a) It is interesting if a steaming swap
        if tx.is_streaming:
            if tx.full_volume_in_rune >= self.min_streaming_swap_usd / usd_per_rune:
                return True

        # b) It is interesting if paid much to affiliate fee collector
        affiliate_fee_rune = tx.meta_swap.affiliate_fee * tx.full_volume_in_rune
        if affiliate_fee_rune >= self.aff_fee_min_usd / usd_per_rune:
            return True

        # c) It is interesting if the Dex aggregator used
        if tx.dex_aggregator_used and tx.full_volume_in_rune >= self.dex_min_usd / usd_per_rune:
            return True

        # d) If we announce that the streaming swap has started, then we should announce that it's finished,
        # regardless of its volume.
        if tx.tx_hash in self._ss_txs_started:
            return True

        # e) If trade asset involved
        if tx.is_trade_asset_involved:
            if tx.full_volume_in_rune >= self.min_trade_asset_swap_usd / usd_per_rune:
                return True

        # f) Regular rules are applied
        return super().is_tx_suitable(tx, min_rune_volume, usd_per_rune, curve_mult)


class RefundTxNotifier(GenericTxNotifier):
    def __init__(self, deps: DepContainer, params: SubConfig, curve: DepthCurve):
        super().__init__(deps, params, (ActionType.REFUND,), curve)
        self.cd_period = params.as_interval('cooldown', 5 * MINUTE)

        # Deduplicator with cooldown for each tx sender
        self.deduplicator = TxDeduplicatorSenderCooldown(
            deps.db, DB_KEY_TX_ANNOUNCED_HASHES,
            'Refund',
            self.cd_period
        )
