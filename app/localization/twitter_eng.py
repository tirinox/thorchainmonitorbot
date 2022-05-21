from typing import List

from aiothornode.types import ThorChainInfo
from semver import VersionInfo

from localization.base import BaseLocalization
from services.lib.constants import thor_to_float, rune_origin
from services.lib.date_utils import now_ts
from services.lib.money import Asset, short_dollar, format_percent, pretty_money, pretty_dollar, pretty_rune, \
    RAIDO_GLYPH, calc_percent_change, adaptive_round_to_str, emoji_for_percent_change
from services.lib.texts import x_ses
from services.models.bep2 import BEP2CEXFlow, BEP2Transfer
from services.models.cap_info import ThorCapInfo
from services.models.last_block import EventBlockSpeed
from services.models.mimir import MimirChange, MimirHolder, MimirVoting, MimirVoteOption
from services.models.net_stats import NetworkStats
from services.models.node_info import NodeSetChanges, NodeVersionConsensus
from services.models.pool_info import PoolDetailHolder, PoolChanges, PoolInfo
from services.models.price import RuneMarketInfo, PriceReport
from services.models.tx import ThorTxExtended, ThorTxType


class TwitterEnglishLocalization(BaseLocalization):
    def notification_text_cap_change(self, old: ThorCapInfo, new: ThorCapInfo):
        up = old.cap < new.cap
        verb = "has been increased" if up else "has been decreased"
        arrow = '⬆️' if up else '⚠️ ⬇️'
        call = "Come on, add more liquidity!\n" if up else ''
        message = (
            f'{arrow} Pool cap {verb} from {pretty_money(old.cap)} to {pretty_money(new.cap)}!\n'
            f'Currently {pretty_money(new.pooled_rune)} {self.R} are in the liquidity pools.\n'
            f"{self._cap_progress_bar(new)}\n"
            f'🤲🏻 You can add {pretty_money(new.how_much_rune_you_can_lp) + " " + RAIDO_GLYPH} {self.R} '
            f'or {pretty_dollar(new.how_much_usd_you_can_lp)}.\n'
            f'The price of {self.R} in the pools is ${new.price:.3f}.\n'
            f'{call}'
        )
        return message

    def notification_text_cap_opened_up(self, cap: ThorCapInfo):
        return (
            '💡 There is free space in liquidity pools!\n'
            f'{pretty_money(cap.pooled_rune)} {self.R} of '
            f"{pretty_money(cap.cap)} {self.R} max pooled.\n"
            f"{self._cap_progress_bar(cap)}\n"
            f'🤲🏻 You can add {pretty_rune(cap.how_much_rune_you_can_lp)} {self.R} '
            f'or {pretty_dollar(cap.how_much_usd_you_can_lp)}.'
        )

    @staticmethod
    def tx_convert_string(tx: ThorTxExtended, usd_per_rune):
        inputs = tx.get_asset_summary(in_only=True)
        outputs = tx.get_asset_summary(out_only=True)

        input_str = ', '.join(f"{pretty_money(amount)} {asset}" for asset, amount in inputs.items())
        output_str = ', '.join(f"{pretty_money(amount)} {asset}" for asset, amount in outputs.items())

        return f"{input_str} ➡️ {output_str} ({pretty_dollar(tx.get_usd_volume(usd_per_rune))})"

    def notification_text_large_single_tx(self, tx: ThorTxExtended, usd_per_rune: float,
                                          pool_info: PoolInfo,
                                          cap: ThorCapInfo = None):
        (ap, asset_side_usd_short, chain, percent_of_pool, pool_depth_usd, rp, rune_side_usd_short,
         total_usd_volume) = self.lp_tx_calculations(usd_per_rune, pool_info, tx)

        heading = ''
        if tx.type == ThorTxType.TYPE_ADD_LIQUIDITY:
            heading = f'🐳 Whale added liquidity 🟢'
        elif tx.type == ThorTxType.TYPE_WITHDRAW:
            heading = f'🐳 Whale removed liquidity 🔴'
        elif tx.type == ThorTxType.TYPE_DONATE:
            heading = f'🙌 Donation to the pool'
        elif tx.type == ThorTxType.TYPE_SWAP:
            heading = f'🐳 Large swap 🔁'
        elif tx.type == ThorTxType.TYPE_REFUND:
            heading = f'🐳 Big refund ↩️❗'
        elif tx.type == ThorTxType.TYPE_SWITCH:
            heading = f'🐳 Large Rune switch 🆙'

        asset = Asset(tx.first_pool).name

        content = ''
        if tx.type in (ThorTxType.TYPE_ADD_LIQUIDITY, ThorTxType.TYPE_WITHDRAW, ThorTxType.TYPE_DONATE):
            if tx.affiliate_fee > 0:
                aff_fee_usd = tx.get_affiliate_fee_usd(usd_per_rune)
                mark = self._exclamation_sign(aff_fee_usd, 'fee_usd_limit')
                aff_text = f'Affiliate fee: {short_dollar(aff_fee_usd)}{mark} ' \
                           f'({format_percent(tx.affiliate_fee)})\n'
            else:
                aff_text = ''

            ilp_rune = tx.meta_withdraw.ilp_rune if tx.meta_withdraw else 0
            if ilp_rune > 0:
                ilp_rune_fmt = pretty_money(ilp_rune, postfix=" " + self.R)
                ilp_text = f'🛡️ IL protection paid: {ilp_rune_fmt} ' \
                           f'({pretty_dollar(ilp_rune * usd_per_rune)})\n'
            else:
                ilp_text = ''

            content = (
                f"{pretty_money(tx.rune_amount)} {self.R} ({rp:.0f}% = {rune_side_usd_short}) ↔️ "
                f"{pretty_money(tx.asset_amount)} {asset} "
                f"({ap:.0f}% = {asset_side_usd_short})\n"
                f"Total: ${pretty_money(total_usd_volume)} ({percent_of_pool:.2f}% of the whole pool).\n"
                f"{aff_text}"
                f"{ilp_text}"
                f"Pool depth is ${pretty_money(pool_depth_usd)} now."
            )
        elif tx.type == ThorTxType.TYPE_SWITCH:
            # [Amt] Rune [Blockchain: ERC20/BEP2] -> [Amt] THOR Rune ($usd)
            if tx.first_input_tx and tx.first_output_tx:
                amt = thor_to_float(tx.first_input_tx.first_amount)
                origin = rune_origin(tx.first_input_tx.first_asset)
                content = (
                    f"{pretty_money(amt)} {origin} {self.R} ➡️ {pretty_money(amt)} Native {self.R} "
                    f"({pretty_dollar(tx.get_usd_volume(usd_per_rune))})"
                )
        elif tx.type == ThorTxType.TYPE_REFUND:
            content = (
                    self.tx_convert_string(tx, usd_per_rune) +
                    f"\nReason: {tx.meta_refund.reason[:30]}.."
            )
        elif tx.type == ThorTxType.TYPE_SWAP:
            content = self.tx_convert_string(tx, usd_per_rune)
            slip_str = f'{tx.meta_swap.trade_slip_percent:.3f} %'
            l_fee_usd = tx.meta_swap.liquidity_fee_rune_float * usd_per_rune

            if tx.affiliate_fee > 0:
                aff_fee_usd = tx.get_affiliate_fee_usd(usd_per_rune)
                mark = self._exclamation_sign(aff_fee_usd, 'fee_usd_limit')
                aff_text = f'Affiliate fee: {short_dollar(aff_fee_usd)}{mark} ' \
                           f'({format_percent(tx.affiliate_fee)})\n'
            else:
                aff_text = ''

            slip_mark = self._exclamation_sign(l_fee_usd, 'slip_usd_limit')
            content += (
                f"\n{aff_text}"
                f"Slip: {slip_str}, "
                f"liquidity fee: {pretty_dollar(l_fee_usd)}{slip_mark}"
            )

        msg = f"{heading}\n{content}"

        if cap:
            msg += (
                f"\n\n"
                f"Liquidity cap is {self._cap_progress_bar(cap)} full now.\n"
                f'You can add {pretty_money(cap.how_much_rune_you_can_lp)} {self.R} '
                f'({pretty_dollar(cap.how_much_usd_you_can_lp)}) more.\n'
            )

        return msg.strip()

    def notification_text_queue_update(self, item_type, step, value):
        if step == 0:
            return f"☺️ Queue [{item_type}] is empty again!"
        else:
            return (
                f"🤬 Attention! Queue [{item_type}] has {value} transactions!\n"
                f"[{item_type}] transactions may be delayed."
            )

    def notification_text_price_update(self, p: PriceReport, ath=False, halted_chains=None):
        title = '💲 Price update' if not ath else '🚀 A new all-time high has been achieved!'

        message = f"{title}\n"

        if halted_chains:
            hc = ', '.join(halted_chains)
            message += f"🚨 Trading is still halted on {hc}.\n"

        price = p.market_info.pool_rune_price

        pr_text = f"${price:.3f}"
        btc_price = f"₿ {p.btc_pool_rune_price:.8f}"
        message += f"RUNE price is {pr_text} ({btc_price}) now.\n"

        fp = p.market_info

        if fp.cex_price > 0.0:
            message += f"RUNE price at Binance (CEX) is {pretty_dollar(fp.cex_price)} " \
                       f"(RUNE/USDT market).\n"

            div, div_p, exclamation = self.price_div_calc(fp)
            message += f"Divergence of Native vs BEP2 is {pretty_dollar(div)} ({div_p:.1f}%{exclamation}).\n"

        last_ath = p.last_ath
        if last_ath is not None and ath:
            last_ath_pr = f'{last_ath.ath_price:.2f}'
            ago_str = self.format_time_ago(now_ts() - last_ath.ath_date)
            message += f"Last ATH was ${last_ath_pr} ({ago_str}).\n"

        time_combos = zip(
            ('1h', '24h', '7d'),
            (p.price_1h, p.price_24h, p.price_7d)
        )
        for title, old_price in time_combos:
            if old_price:
                pc = calc_percent_change(old_price, price)
                message += f"{title.rjust(4)}:{adaptive_round_to_str(pc, True).rjust(8)} % " \
                           f"{emoji_for_percent_change(pc).ljust(4).rjust(6)}\n"

        if fp.rank >= 1:
            message += f"Coin market cap is {pretty_dollar(fp.market_cap)} (#{fp.rank})\n"

        if fp.total_trade_volume_usd > 0:
            message += f"Total trading volume is {pretty_dollar(fp.total_trade_volume_usd)}\n"

        message += '\n'

        if fp.tlv_usd >= 1:
            message += (f"TVL of non-RUNE assets: ${pretty_money(fp.tlv_usd)}\n"
                        f"So deterministic price of RUNE is {pretty_money(fp.fair_price, prefix='$')}\n"
                        f"Speculative multiplier is {x_ses(fp.fair_price, price)}\n")

        return message.rstrip()

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
