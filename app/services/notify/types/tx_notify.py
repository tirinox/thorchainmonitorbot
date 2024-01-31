import asyncio
from contextlib import suppress
from typing import List, Optional

from redis.asyncio import Redis

from aionode.types import ThorSwapperClout
from services.jobs.scanner.event_db import EventDatabase
from services.lib.config import SubConfig
from services.lib.cooldown import Cooldown
from services.lib.date_utils import parse_timespan_to_seconds, MINUTE
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.money import Asset, DepthCurve, pretty_dollar
from services.lib.utils import WithLogger
from services.models.tx import ThorTx, EventLargeTransaction
from services.models.tx_type import TxType
from services.notify.types.cap_notify import LiquidityCapNotifier


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
        self.no_repeat_protection = True

    DB_KEY_ANNOUNCED_TX_ID = 'tx:announced-hashes'

    async def mark_as_announced(self, tx_id, clear=False):
        if not tx_id:
            return

        r: Redis = self.deps.db.redis
        if clear:
            await r.srem(self.DB_KEY_ANNOUNCED_TX_ID, tx_id)
        else:
            await r.sadd(self.DB_KEY_ANNOUNCED_TX_ID, tx_id)

    async def is_announced(self, tx_id):
        if not tx_id:
            return True

        r: Redis = self.deps.db.redis
        return await r.sismember(self.DB_KEY_ANNOUNCED_TX_ID, tx_id)

    async def on_data(self, senders, txs: List[ThorTx]):
        with suppress(Exception):
            await self.handle_txs_unsafe(senders, txs)

    async def _only_new_transactions(self, txs: List[ThorTx]):
        flags = await asyncio.gather(*[self.is_announced(tx.tx_hash) for tx in txs])
        tmp_txs = []
        for flag, tx in zip(flags, txs):
            if flag:
                self.logger.warning(f'Tx {tx.tx_hash} ({tx.type}) has been already announced. Ignore!')
            else:
                tmp_txs.append(tx)
        return tmp_txs

    async def handle_txs_unsafe(self, senders, txs: List[ThorTx]):
        # 1. filter irrelevant tx types
        txs = [tx for tx in txs if tx.type in self.tx_types]  # filter my TX types

        # 2. Throw away announced Txs in the past
        if self.no_repeat_protection:
            txs = await self._only_new_transactions(txs)

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

            await self.pass_data_to_listeners(event)

            if self.no_repeat_protection:
                await self.mark_as_announced(tx.tx_hash)

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
            if tx.type != TxType.REFUND:
                self.logger.warning(f'No pool depth for Tx: {tx}.')
            min_share_rune_volume = 0.0
        else:
            if self.curve:
                curve_mult = curve_mult or self.curve_mult
                min_pool_share = self.curve.evaluate(pool_usd_depth) * curve_mult
                min_share_rune_volume = pool_usd_depth / usd_per_rune * min_pool_share
            else:
                min_share_rune_volume = 0.0

        if tx.full_rune >= min_rune_volume and tx.full_rune >= min_share_rune_volume:
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
        super().__init__(deps, params, (TxType.WITHDRAW, TxType.ADD_LIQUIDITY), curve)
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
        super().__init__(deps, params, (TxType.SWAP,), curve)
        self.dex_min_usd = params.as_float('also_trigger_when.dex_aggregator_used.min_usd_total', 500)
        self.aff_fee_min_usd = params.as_float('also_trigger_when.affiliate_fee_usd_greater', 500)
        self.min_streaming_swap_usd = params.as_float('also_trigger_when.streaming_swap.volume_greater', 2500)
        self._txs_started = []  # Fill it every tick before is_tx_suitable is called.
        self._ev_db = EventDatabase(deps.db)

    async def _check_if_they_announced_as_started(self, txs: List[ThorTx]):
        if not txs:
            return

        tx_ids = [tx.tx_hash for tx in txs]

        flags = await asyncio.gather(
            *[self._ev_db.is_announced_as_started(tx_id) for tx_id in tx_ids]
        )
        self._txs_started = set(tx_id for tx_id, flag in zip(tx_ids, flags) if flag)
        if self._txs_started:
            self.logger.info(f'These Txs were announced as started SS: {self._txs_started}')

    async def handle_txs_unsafe(self, senders, txs: List[ThorTx]):
        await self._check_if_they_announced_as_started(txs)

        return await super().handle_txs_unsafe(senders, txs)

    def is_tx_suitable(self, tx: ThorTx, min_rune_volume, usd_per_rune, curve_mult=None):
        # a) It is interesting if a steaming swap
        if tx.is_streaming:
            if tx.full_rune >= self.min_streaming_swap_usd / usd_per_rune:
                return True

        # b) It is interesting if paid much to affiliate fee collector
        affiliate_fee_rune = tx.meta_swap.affiliate_fee * tx.full_rune
        if affiliate_fee_rune >= self.aff_fee_min_usd / usd_per_rune:
            return True

        # c) It is interesting if the Dex aggregator used
        if tx.dex_aggregator_used and tx.full_rune >= self.dex_min_usd / usd_per_rune:
            return True

        # d) If we announce that the streaming swap has started, then we should announce that it's finished,
        # regardless of its volume.
        if tx.tx_hash in self._txs_started:
            return True

        # e) Regular rules are applied
        return super().is_tx_suitable(tx, min_rune_volume, usd_per_rune, curve_mult)


class RefundTxNotifier(GenericTxNotifier):
    def __init__(self, deps: DepContainer, params: SubConfig, curve: DepthCurve):
        super().__init__(deps, params, (TxType.REFUND,), curve)
        cd_period = params.as_interval('cooldown', 5 * MINUTE)
        self.refund_cd = Cooldown(deps.db, 'Refund', cd_period)

    async def is_announced(self, tx_id):
        before = await super().is_announced(tx_id)
        if before:
            return True

        if not await self.refund_cd.can_do():
            self.logger.warning(f'Refund announcement cooldown went off!')
            return True

        await self.refund_cd.do()
        return False
