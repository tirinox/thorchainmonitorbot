from typing import List

from aiothornode.types import ThorChainInfo
from semver import VersionInfo

from localization.achievements.ach_tw_eng import AchievementsTwitterEnglishLocalization
from localization.eng_base import BaseLocalization
from services.dialog.twitter.text_length import twitter_intelligent_text_splitter
from services.jobs.fetch.circulating import SupplyEntry
from services.lib.config import Config
from services.lib.constants import thor_to_float, rune_origin, Chains
from services.lib.date_utils import now_ts, seconds_human
from services.lib.explorers import get_explorer_url_to_tx
from services.lib.midgard.name_service import NameMap, add_thor_suffix
from services.lib.money import Asset, short_dollar, format_percent, pretty_money, pretty_dollar, RAIDO_GLYPH, \
    calc_percent_change, adaptive_round_to_str, emoji_for_percent_change, short_address, short_money, short_rune, \
    pretty_percent, chart_emoji
from services.lib.texts import x_ses, progressbar, plural, bracketify, up_down_arrow, \
    bracketify_spaced, shorten_text
from services.lib.w3.dex_analytics import DexReportEntry, DexReport
from services.models.cap_info import ThorCapInfo
from services.models.killed_rune import KilledRuneEntry
from services.models.last_block import EventBlockSpeed, BlockProduceState
from services.models.mimir import MimirChange, MimirHolder
from services.models.mimir_naming import MimirUnits
from services.models.net_stats import NetworkStats
from services.models.node_info import NodeSetChanges, NodeVersionConsensus, NodeInfo
from services.models.pol import EventPOL
from services.models.pool_info import PoolMapPair, PoolChanges, PoolInfo
from services.models.price import RuneMarketInfo, PriceReport
from services.models.savers import EventSaverStats
from services.models.transfer import RuneCEXFlow, RuneTransfer
from services.models.tx import ThorTx, ThorTxType
from services.notify.channel import MESSAGE_SEPARATOR


class TwitterEnglishLocalization(BaseLocalization):
    def __init__(self, cfg: Config):
        super().__init__(cfg)
        self.ach = AchievementsTwitterEnglishLocalization()

    TEXT_DECORATION_ENABLED = False

    @classmethod
    def smart_split(cls, parts):
        parts = twitter_intelligent_text_splitter(parts)
        return MESSAGE_SEPARATOR.join(parts).strip()

    PIC_NODE_DIVERSITY_BY_PROVIDER_CAPTION = 'THORChain nodes'

    def notification_text_cap_change(self, old: ThorCapInfo, new: ThorCapInfo):
        up = old.cap < new.cap
        verb = "has been increased" if up else "has been decreased"
        arrow = '⬆️' if up else '⚠️ ⬇️'
        call = "Come on, add more liquidity!\n" if up else ''
        message = (
            f'{arrow} Pool cap {verb} from {short_money(old.cap)} to {short_money(new.cap)}!\n'
            f'Currently {short_money(new.pooled_rune)} {self.R} are in the liquidity pools.\n'
            f"{self._cap_progress_bar(new)}\n"
            f'🤲🏻 You can add {short_money(new.how_much_rune_you_can_lp) + " " + RAIDO_GLYPH} {self.R} '
            f'or {short_dollar(new.how_much_usd_you_can_lp)}.\n'
            f'The price of {self.R} in the pools is ${new.price:.3f}.\n'
            f'{call}'
        )
        return message

    def notification_text_cap_full(self, cap: ThorCapInfo):
        return (
            '🙆‍♀️ Liquidity has reached the capacity limit!\n'
            'Please stop adding liquidity. '
            'You will get refunded if you provide liquidity from now on!\n'
            f'Now {short_money(cap.pooled_rune)} {self.R} of '
            f"{short_money(cap.cap)} {self.R} max pooled ({format_percent(cap.pooled_rune, cap.cap)})"
        )

    def notification_text_cap_opened_up(self, cap: ThorCapInfo):
        return (
            '💡 There is free space in liquidity pools!\n'
            f'{short_money(cap.pooled_rune)} {self.R} of '
            f"{short_money(cap.cap)} {self.R} max pooled ({format_percent(cap.pooled_rune, cap.cap)})\n"
            f'🤲🏻 You can add {short_money(cap.how_much_rune_you_can_lp)} {self.R} '
            f'or {short_dollar(cap.how_much_usd_you_can_lp)}.'
        )

    @staticmethod
    def format_op_amount(amt):
        return short_money(amt)

    def notification_text_large_single_tx(self, tx: ThorTx,
                                          usd_per_rune: float,
                                          pool_info: PoolInfo,
                                          cap: ThorCapInfo = None,
                                          name_map: NameMap = None,
                                          mimir: MimirHolder = None):
        (ap, asset_side_usd_short, chain, percent_of_pool, pool_depth_usd, rp, rune_side_usd_short,
         total_usd_volume) = self.lp_tx_calculations(usd_per_rune, pool_info, tx)

        heading = ''

        if tx.type == ThorTxType.TYPE_ADD_LIQUIDITY:
            if tx.is_savings:
                heading = f'🐳→💰 Add to savings vault'
            else:
                heading = f'🐳→⚡ Add liquidity'
        elif tx.type == ThorTxType.TYPE_WITHDRAW:
            if tx.is_savings:
                heading = f'🐳←💰 Withdraw from savings vault'
            else:
                heading = f'🐳←⚡ Withdraw liquidity'
        elif tx.type == ThorTxType.TYPE_DONATE:
            heading = f'🐳 Donation to the pool 🙌'
        elif tx.type == ThorTxType.TYPE_SWAP:
            heading = f'🐳 Swap 🔁'
        elif tx.type == ThorTxType.TYPE_REFUND:
            heading = f'🐳 Refund ↩️❗'
        elif tx.type == ThorTxType.TYPE_SWITCH:
            heading = f'🐳 Switch 🆙'

        if tx.is_pending:
            heading += ' [Pending]'

        # it is old
        if date_text := self.tx_date(tx):
            heading += f' {date_text}'

        asset = self.pretty_asset(tx.first_pool)

        content = f'👤{self.link_to_address(tx.sender_address, name_map)}: '

        if tx.type in (ThorTxType.TYPE_ADD_LIQUIDITY, ThorTxType.TYPE_WITHDRAW, ThorTxType.TYPE_DONATE):
            if tx.affiliate_fee > 0:
                aff_fee_usd = tx.get_affiliate_fee_usd(usd_per_rune)
                mark = self._exclamation_sign(aff_fee_usd, 'fee_usd_limit')
                aff_text = f'Aff. fee: {short_dollar(aff_fee_usd)}{mark} ' \
                           f'({format_percent(tx.affiliate_fee)})\n'
            else:
                aff_text = ''

            ilp_rune = tx.meta_withdraw.ilp_rune if tx.meta_withdraw else 0
            if ilp_rune > 0:
                ilp_usd = ilp_rune * usd_per_rune
                ilp_rune_fmt = short_rune(ilp_rune)
                mark = self._exclamation_sign(ilp_usd, 'ilp_usd_limit')
                ilp_text = f'🛡️ IL prot. paid: {ilp_rune_fmt}{mark} ' \
                           f'({short_dollar(ilp_usd)})\n'
            else:
                ilp_text = ''

            if tx.is_savings:
                rune_part = ''
                asset_part = f"{short_money(tx.asset_amount)} {asset}"
                amount_more, asset_more, saver_pb, saver_cap, saver_percent = \
                    self.get_savers_limits(pool_info, usd_per_rune, mimir, tx.asset_amount)
                pool_depth_part = f'Savers cap is {saver_pb} full. '
                if amount_more > 0:
                    pool_depth_part += f'You can add {short_money(amount_more)} {asset_more} more.'
                pool_percent_part = f" ({saver_percent:.2f}% of vault)" if saver_percent > self.MIN_PERCENT_TO_SHOW \
                    else ''
            else:
                rune_part = f"{short_money(tx.rune_amount)} {self.R} ({rune_side_usd_short}) ↔️ "
                asset_part = f"{short_money(tx.asset_amount)} {asset} ({asset_side_usd_short})"
                pool_depth_part = f'Pool depth is {short_dollar(pool_depth_usd)} now.'
                pool_percent_part = f" ({percent_of_pool:.2f}% of pool)" if percent_of_pool > 0.01 else ''

            content += (
                f"{rune_part}{asset_part}\n"
                f"Total: {short_dollar(total_usd_volume)}{pool_percent_part}\n"
                f"{aff_text}"
                f"{ilp_text}"
                f"{pool_depth_part}"
            )
        elif tx.type == ThorTxType.TYPE_SWITCH:
            # [Amt] Rune [Blockchain: ERC20/BEP2] -> [Amt] THOR Rune ($usd)
            if tx.first_input_tx and tx.first_output_tx:
                amt = thor_to_float(tx.first_input_tx.first_amount)
                origin = rune_origin(tx.first_input_tx.first_asset)
                content += (
                    f"{short_money(amt)} {origin} {self.R} ➡️ {short_money(amt)} Native {self.R} "
                    f"({short_dollar(tx.get_usd_volume(usd_per_rune))})"
                )

            in_rune_amt = tx.asset_amount
            out_rune_amt = tx.rune_amount
            killed_rune = max(0.0, in_rune_amt - out_rune_amt)
            killed_usd_str = short_dollar(killed_rune * usd_per_rune)
            killed_percent_str = format_percent(killed_rune, in_rune_amt)
            origin = rune_origin(tx.first_input_tx.first_asset)
            content = (
                f"{short_money(in_rune_amt)} {origin} {self.R} ➡️ "
                f"{short_money(out_rune_amt)} Native {self.R} "
                f"({short_dollar(tx.get_usd_volume(usd_per_rune))})"
            )
            if killed_rune > 0:
                content += f'\n☠️ Killed {short_rune(killed_rune)} ({killed_percent_str} or {killed_usd_str})!'

        elif tx.type == ThorTxType.TYPE_REFUND:
            reason = shorten_text(tx.meta_refund.reason, 30)
            content += (
                    self.format_swap_route(tx, usd_per_rune, dollar_assets=True) +
                    f"\nReason: {reason}.."
            )
        elif tx.type == ThorTxType.TYPE_SWAP:
            content += self.format_swap_route(tx, usd_per_rune, dollar_assets=True)
            slip_str = f'{tx.meta_swap.trade_slip_percent:.3f} %'
            l_fee_usd = tx.meta_swap.liquidity_fee_rune_float * usd_per_rune

            if tx.affiliate_fee > 0:
                aff_fee_usd = tx.get_affiliate_fee_usd(usd_per_rune)
                mark = self._exclamation_sign(aff_fee_usd, 'fee_usd_limit')
                aff_text = f'Aff. fee: {short_dollar(aff_fee_usd)}{mark} ' \
                           f'({format_percent(tx.affiliate_fee)})\n'
            else:
                aff_text = ''

            slip_mark = self._exclamation_sign(l_fee_usd, 'slip_usd_limit')
            content += (
                f"\n{aff_text}"
                f"Slip: {slip_str}, "
                f"liq. fee: {short_dollar(l_fee_usd)}{slip_mark}"
            )

        link = get_explorer_url_to_tx(self.cfg.network_id, Chains.THOR, tx.first_input_tx_hash) \
            if tx and tx.first_input_tx_hash else ''

        msg = f"{heading}\n" \
              f"{content}\n" \
              f"{link}"

        return msg.strip()

    def cap_message(self, cap: ThorCapInfo):
        return (
            f"\n\n"
            f"Liq. cap is {format_percent(cap.pooled_rune, cap.cap)} full now.\n"
            f'You can add {short_money(cap.how_much_rune_you_can_lp)} {self.R} '
            f'({short_dollar(cap.how_much_usd_you_can_lp)}) more.\n'
        )

    def notification_text_queue_update(self, item_type, is_free, value):
        if is_free:
            return f"☺️ Queue [{item_type}] is empty again!"
        else:
            if item_type != 'internal':
                extra = f"\n[{item_type}] transactions may be delayed."
            else:
                extra = ''

            return f"🤬 Attention! Queue [{item_type}] has {value} transactions!{extra}"

    def notification_text_price_update(self, p: PriceReport, ath=False, halted_chains=None):
        message = '🚀 New all-time high!\n' if ath else ''

        # if halted_chains:
        #     hc = ', '.join(halted_chains)
        #     message += f"🚨 Trading is still halted on {hc}.\n"

        price = p.market_info.pool_rune_price

        btc_price = f"₿ {p.btc_pool_rune_price:.8f}"
        message += f"RUNE price is {price:.3f} ({btc_price}) now\n"

        fp = p.market_info

        if fp.cex_price > 0.0:
            message += f"{self.ref_cex_pair} {self.ref_cex_name}: {pretty_dollar(fp.cex_price)}\n"

            div, div_p = fp.divergence_abs, fp.divergence_percent
            exclamation = self._exclamation_sign(div_p, ref=10)
            message += f"Divergence: {div_p:.1f}%{exclamation}\n"

        last_ath = p.last_ath
        if last_ath is not None and ath:
            last_ath_pr = f'{last_ath.ath_price:.2f}'
            ago_str = self.format_time_ago(now_ts() - last_ath.ath_date)
            message += f"Last ATH: ${last_ath_pr} ({ago_str}).\n"

        time_combos = zip(
            ('1h', '24h', '7d'),
            (p.price_1h, p.price_24h, p.price_7d)
        )
        for title, old_price in time_combos:
            if old_price:
                pc = calc_percent_change(old_price, price)
                message += f"{title.rjust(4)}: {adaptive_round_to_str(pc, True)}% " \
                           f"{emoji_for_percent_change(pc)}\n"

        if fp.rank >= 1:
            message += f"Mrkt. cap: {short_dollar(fp.market_cap)} (#{fp.rank})\n"

        if fp.total_trade_volume_usd > 0:
            message += f'24h vol.: {short_dollar(fp.total_trade_volume_usd)}\n'

        if fp.tlv_usd >= 1:
            message += (
                f"Det. price: {pretty_dollar(fp.fair_price)}\n"
                f"Spec. mult.: {x_ses(fp.fair_price, price)}\n")

        return message.rstrip()

    def notification_text_price_divergence(self, info: RuneMarketInfo, normal: bool):
        title = f'〰️ Low {self.R} price divergence!' if normal else f'🔺 High {self.R} price divergence!'

        div, div_p = info.divergence_abs, info.divergence_percent
        exclamation = self._exclamation_sign(div_p, ref=10)

        text = (
            f"🖖 {title}\n"
            f"CEX (BEP2) Rune price is {pretty_dollar(info.cex_price)}\n"
            f"Weighted average Rune price over liquidity pools is {pretty_dollar(info.pool_rune_price)}\n"
            f"Divergence is {pretty_dollar(div)} ({div_p:.1f}%{exclamation})."
        )
        return text

    def notification_text_pool_churn(self, pc: PoolChanges):
        if pc.pools_changed:
            message = '🏊 Liquidity pool churn!' + '\n'
        else:
            message = ''

        def pool_text(pool_name, status, to_status=None, can_swap=True):
            if can_swap and PoolInfo.is_status_enabled(to_status):
                extra = '🎉 BECAME ACTIVE!'
            else:
                extra = status
                if to_status is not None and status != to_status:  # fix: staged -> staged
                    extra += f' → {to_status}'
                extra = f'({extra})'
            return f'  • {Asset(pool_name).pretty_str}: {extra}'

        if pc.pools_added:
            message += '✅ Pools added:\n' + '\n'.join([pool_text(*a) for a in pc.pools_added]) + '\n'
        if pc.pools_removed:
            message += ('❌ Pools removed:\n' + '\n'.join([pool_text(*a, can_swap=False) for a in pc.pools_removed])
                        + '\n')
        if pc.pools_changed:
            message += '🔄 Pools changed:\n' + '\n'.join([pool_text(*a) for a in pc.pools_changed]) + '\n'

        message += 'https://thorchain.net/pools/'

        return message.rstrip()

    def notification_text_network_summary(self,
                                          old: NetworkStats, new: NetworkStats,
                                          market: RuneMarketInfo,
                                          killed: KilledRuneEntry):
        parts = []

        message = '🌐 THORChain stats\n'

        security_text = self.network_bond_security_text(new.network_security_ratio)
        message += f'Network is {security_text}.\n'

        active_nodes_change = bracketify_spaced(up_down_arrow(old.active_nodes, new.active_nodes, int_delta=True))
        standby_nodes_change = bracketify_spaced(up_down_arrow(old.active_nodes, new.active_nodes, int_delta=True))
        message += f"{new.active_nodes} active nodes{active_nodes_change}" \
                   f"and {new.standby_nodes} standby nodes{standby_nodes_change}\n"

        parts.append(message)

        # -- BOND

        current_active_bond_text = short_rune(new.total_active_bond_rune)
        current_active_bond_change = bracketify(
            up_down_arrow(old.total_active_bond_rune, new.total_active_bond_rune, money_delta=True))

        current_bond_usd_text = short_dollar(new.total_active_bond_usd)
        current_bond_usd_change = bracketify(
            up_down_arrow(old.total_active_bond_usd, new.total_active_bond_usd, money_delta=True, money_prefix='$')
        )

        current_total_bond_text = short_rune(new.total_bond_rune)
        current_total_bond_change = bracketify(
            up_down_arrow(old.total_bond_rune, new.total_bond_rune, money_delta=True))

        current_total_bond_usd_text = short_dollar(new.total_bond_usd)
        current_total_bond_usd_change = bracketify(
            up_down_arrow(old.total_bond_usd, new.total_bond_usd, money_delta=True, money_prefix='$')
        )

        message = f"🔗 Active bond: {current_active_bond_text}{current_active_bond_change} or " \
                  f"{current_bond_usd_text}{current_bond_usd_change}.\n"

        parts.append(message)

        message = f"Total bond: {current_total_bond_text}{current_total_bond_change} or " \
                  f"{current_total_bond_usd_text}{current_total_bond_usd_change}.\n"

        parts.append(message)

        # -- POOL

        current_pooled_text = short_rune(new.total_rune_pooled)
        current_pooled_change = bracketify(
            up_down_arrow(old.total_rune_pooled, new.total_rune_pooled, money_delta=True))

        current_pooled_usd_text = short_dollar(new.total_pooled_usd)
        current_pooled_usd_change = bracketify(
            up_down_arrow(old.total_pooled_usd, new.total_pooled_usd, money_delta=True, money_prefix='$'))

        message = f"🏊 Total pooled: {current_pooled_text}{current_pooled_change} or " \
                  f"{current_pooled_usd_text}{current_pooled_usd_change}.\n"

        current_liquidity_usd_text = short_dollar(new.total_liquidity_usd)
        current_liquidity_usd_change = bracketify(
            up_down_arrow(old.total_liquidity_usd, new.total_liquidity_usd, money_delta=True, money_prefix='$'))

        message += f"🌊 Total liquidity (TVL): {current_liquidity_usd_text}{current_liquidity_usd_change}.\n"

        parts.append(message)

        # -- TVL

        tlv_change = bracketify(
            up_down_arrow(old.total_locked_usd, new.total_locked_usd, money_delta=True, money_prefix='$'))
        message = f'🏦 TVL + Bond: {short_dollar(new.total_locked_usd)}{tlv_change}.\n'
        parts.append(message)

        # -- RESERVE

        reserve_change = bracketify(up_down_arrow(old.reserve_rune, new.reserve_rune,
                                                  postfix=RAIDO_GLYPH, money_delta=True))

        message = f'💰 Reserve: {short_rune(new.reserve_rune)}{reserve_change}.\n'
        parts.append(message)

        # --------------------------------------------------------------------------------------------------------------

        # --- FLOWS:

        if old.is_ok:
            # 24 h Add/withdrawal
            added_24h_rune = new.added_rune - old.added_rune
            withdrawn_24h_rune = new.withdrawn_rune - old.withdrawn_rune
            swap_volume_24h_rune = new.swap_volume_rune - old.swap_volume_rune
            switched_24h_rune = new.switched_rune - old.switched_rune

            add_rune_text = short_rune(added_24h_rune)
            withdraw_rune_text = short_rune(withdrawn_24h_rune)
            swap_rune_text = short_rune(swap_volume_24h_rune)
            switch_rune_text = short_rune(switched_24h_rune)

            price = new.usd_per_rune

            add_usd_text = short_dollar(added_24h_rune * price)
            withdraw_usd_text = short_dollar(withdrawn_24h_rune * price)
            swap_usd_text = short_dollar(swap_volume_24h_rune * price)
            switch_usd_text = short_dollar(switched_24h_rune * price)

            message = ''

            if added_24h_rune:
                message += f'➕ Rune added to pools: {add_rune_text} ({add_usd_text}).\n'

            if withdrawn_24h_rune:
                message += f'➖ Rune withdrawn: {withdraw_rune_text} ({withdraw_usd_text}).\n'

            if swap_volume_24h_rune:
                message += f'🔀 Rune swap volume: {swap_rune_text} ({swap_usd_text}) ' \
                           f'in {short_money(new.swaps_24h)} swaps.\n'

            if switched_24h_rune:
                message += f'💎 Rune switched to native: {switch_rune_text} ({switch_usd_text}).\n'

            if message:
                message = f'Last 24 hours:\n' + message

            parts.append(message)

            # synthetics:
            synth_volume_rune = short_rune(new.synth_volume_24h)
            synth_volume_usd = short_dollar(new.synth_volume_24h_usd)
            synth_op_count = short_money(new.synth_op_count)

            message = f'💊 Synth trade volume: {synth_volume_rune} ({synth_volume_usd}) ' \
                      f'in {synth_op_count} swaps\n'

            if new.loss_protection_paid_24h_rune:
                ilp_rune_str = short_rune(new.loss_protection_paid_24h_rune)
                ilp_usd_str = short_dollar(new.loss_protection_paid_24h_rune * new.usd_per_rune)
                message += f'🛡️ ILP payout last 24h: {ilp_rune_str} ({ilp_usd_str})\n'

            parts.append(message)

        message = f'🛡 Total Imp. Loss Protection paid: {(short_dollar(new.loss_protection_paid_usd))}.\n'
        parts.append(message)

        # --------------------------------------------------------------------------------------------------------------

        bonding_apy_change, liquidity_apy_change = self._extract_apy_deltas(new, old)

        message = (
            f'📈 Bonding APY is {pretty_money(new.bonding_apy, postfix="%")}{bonding_apy_change} and '
            f'Liquidity APY is {pretty_money(new.liquidity_apy, postfix="%")}{liquidity_apy_change}.\n'
        )

        parts.append(message)

        if new.users_daily or new.users_monthly:
            daily_users_change = bracketify(up_down_arrow(old.users_daily, new.users_daily, int_delta=True))
            monthly_users_change = bracketify(up_down_arrow(old.users_monthly, new.users_monthly, int_delta=True))
            message = f'👥 Daily users: {new.users_daily}{daily_users_change}, ' \
                      f'monthly users: {new.users_monthly}{monthly_users_change} 🆕\n'
            parts.append(message)

        # --------------------------------------------------------------------------------------------------------------

        active_pool_changes = bracketify(up_down_arrow(old.active_pool_count,
                                                       new.active_pool_count, int_delta=True))
        pending_pool_changes = bracketify(up_down_arrow(old.pending_pool_count,
                                                        new.pending_pool_count, int_delta=True))

        # only if there next pool comes
        if new.next_pool_to_activate:
            message = f'{new.active_pool_count} active pools{active_pool_changes} and ' \
                      f'{new.pending_pool_count} pending pools{pending_pool_changes}.\n'

            next_pool_wait = seconds_human(new.next_pool_activation_ts - now_ts())
            next_pool = self.pool_link(new.next_pool_to_activate)
            message += f"Next pool is likely be activated: {next_pool} in {next_pool_wait}."

            parts.append(message)

        return self.smart_split(parts)

    def _node_bond_change_after_churn(self, changes: NodeSetChanges):
        bond_in, bond_out = changes.bond_churn_in, changes.bond_churn_out
        bond_delta = bond_in - bond_out
        return f'Active bond net change: {short_money(bond_delta, postfix=RAIDO_GLYPH, signed=True)}'

    def notification_text_for_node_churn(self, changes: NodeSetChanges):
        def _format_node_text_plain(node: NodeInfo):
            node_thor_link = short_address(node.node_address, 0)
            return f'{node.flag_emoji}{node_thor_link} ({short_money(node.bond, postfix=RAIDO_GLYPH)})'

        def _make_node_list_plain(nodes, title):
            if not nodes:
                return ''
            message = ', '.join(_format_node_text_plain(node) for node in nodes if node.node_address)
            return f'{title}\n{message}\n'

        components = []

        part1 = _make_node_list_plain(changes.nodes_activated, '➡️ Nodes churned in:')
        components.append(part1)

        part2 = _make_node_list_plain(changes.nodes_deactivated, '⬅️️ Nodes churned out:')
        if changes.nodes_activated or changes.nodes_deactivated:
            part2 += self._node_bond_change_after_churn(changes)
        components.append(part2)

        part3 = _make_node_list_plain(changes.nodes_added, '🆕 New nodes:')
        components.append(part3)

        part4 = _make_node_list_plain(changes.nodes_removed, '🗑️ Nodes disconnected:')
        components.append(part4)

        return self.smart_split(components)

    @staticmethod
    def node_version(v, data: NodeSetChanges, active=True):
        realm = data.active_only_nodes if active else data.nodes_all
        n_nodes = len(data.find_nodes_with_version(realm, v))
        return f"{v} ({n_nodes} {plural(n_nodes, 'node', 'nodes')})"

    def notification_text_version_upgrade_progress(self, data: NodeSetChanges, ver_con: NodeVersionConsensus):
        msg = '🕖 Version upgrade progress\n'

        progress = ver_con.ratio * 100.0
        pb = progressbar(progress, 100.0, 14)

        msg += f'{pb} {progress:.0f} %\n'
        msg += f"{ver_con.top_version_count} of {ver_con.total_active_node_count} nodes " \
               f"upgraded to version {ver_con.top_version}.\n"

        cur_version_txt = self.node_version(data.current_active_version, data)
        msg += f"⚡️ Active protocol version is {cur_version_txt}.\n" + \
               '* Minimum version among all active nodes.'

        return msg

    def notification_text_version_upgrade(self, data: NodeSetChanges, new_versions: List[VersionInfo],
                                          old_active_ver: VersionInfo, new_active_ver: VersionInfo):
        msg = '💫 THORChain protocol version update\n'

        def version_and_nodes(v, nodes_all=False):
            realm = data.nodes_all if nodes_all else data.active_only_nodes
            n_nodes = len(data.find_nodes_with_version(realm, v))
            return f"{v} ({n_nodes} {plural(n_nodes, 'node', 'nodes')})"

        current_active_version = data.current_active_version

        if new_versions:
            new_version_joined = ', '.join(version_and_nodes(v, nodes_all=True) for v in new_versions)
            msg += f"🆕 New version detected: {new_version_joined}\n"

            msg += f"⚡️ Active protocol version is {version_and_nodes(current_active_version)}\n" + \
                   '* Minimum version among all active nodes.\n'

        if old_active_ver != new_active_ver:
            action = 'upgraded' if new_active_ver > old_active_ver else 'downgraded'
            emoji = '🆙' if new_active_ver > old_active_ver else '⬇️'
            msg += (
                f"{emoji} Attention! Active protocol version has been {action} "
                f"from {old_active_ver} to {version_and_nodes(new_active_ver)}\n"
            )

            cnt = data.version_counter(data.active_only_nodes)
            if len(cnt) == 1:
                msg += f"All active nodes run version {current_active_version}\n"
            elif len(cnt) > 1:
                msg += f"The most popular versions are\n"
                for i, (v, count) in enumerate(cnt.most_common(5), start=1):
                    active_node = ' 👈' if v == current_active_version else ''
                    msg += f"{i}. {version_and_nodes(v)} {active_node}\n"
                msg += f"Maximum version available is {version_and_nodes(data.max_available_version)}\n"

        return msg

    TEXT_MIMIR_VOTING_PROGRESS_TITLE = '🏛 Node-Mimir voting update\n\n'

    def notification_text_trading_halted_multi(self, chain_infos: List[ThorChainInfo]):
        msg = ''

        halted_chains = ', '.join(c.chain for c in chain_infos if c.halted)
        if halted_chains:
            msg += f'🚨 Attention! Trading is halted on the {halted_chains} chains! ' \
                   f'Refrain from using it until the trading is restarted! 🚨\n'

        resumed_chains = ', '.join(c.chain for c in chain_infos if not c.halted)
        if resumed_chains:
            msg += f'✅ Heads up! Trading is resumed on the {resumed_chains} chains!'

        return msg.strip()

    def notification_text_block_stuck(self, e: EventBlockSpeed):
        good_time = e.time_without_blocks is not None and e.time_without_blocks > 1
        str_t = self.seconds_human(e.time_without_blocks) if good_time else self.NA
        if e.state == BlockProduceState.StateStuck:
            return f'📛 THORChain block height seems to have stopped increasing!\n' \
                   f'New blocks have not been generated for {str_t}.'
        else:
            return f"🆗 THORChain is producing blocks again!\n" \
                   f"The failure lasted {str_t}."

    def notification_text_block_pace(self, e: EventBlockSpeed):
        phrase = self.get_block_time_state_string(e.state, True)
        block_per_minute = self.format_bps(e.block_speed)

        return (
            f'{phrase}\n'
            f'Presently {block_per_minute} blocks per minute or '
            f'it takes {self.format_block_time(e.block_speed)} seconds to generate a new block.'
        )

    def notification_text_mimir_changed(self, changes: List[MimirChange], mimir: MimirHolder):
        if not changes:
            return ''

        text = '🔔 Mimir update!\n'

        for change in changes:
            units = MimirUnits.get_mimir_units(change.name)
            old_value_fmt = self.format_mimir_value(change.name, change.old_value, units)
            new_value_fmt = self.format_mimir_value(change.name, change.new_value, units)
            name = change.entry.pretty_name if change.entry else change.name

            e = change.entry
            if e:
                if e.source == e.SOURCE_AUTO:
                    text += '[🤖 Auto-solvency ]  '
                elif e.source == e.SOURCE_ADMIN:
                    text += '[👩‍💻 Admins ]  '
                elif e.source == e.SOURCE_NODE:
                    text += '[🤝 Nodes voted ]  '
                elif e.source == e.SOURCE_NODE_CEASED:
                    text += '[💔 Node-Mimir off ]  '

            if change.kind == MimirChange.ADDED_MIMIR:
                text += (
                    f'➕ New Mimir \"{name}\". '
                    f'Default: {old_value_fmt} → New: {new_value_fmt}‼️'
                )
            elif change.kind == MimirChange.REMOVED_MIMIR:
                text += f"➖ Mimir \"{name}\" has been removed. It was {old_value_fmt} before. ‼️"
                if change.new_value is not None:
                    text += f" Now it has its default value: {new_value_fmt}."
            else:
                text += (
                    f"🔄 Mimir \"{name}\" has been updated from "
                    f"{old_value_fmt} → "
                    f"to {new_value_fmt}‼️"
                )
                if change.entry.automatic:
                    text += f' at block #{change.new_value}.'
            text += '\n'

        return text.strip()

    def format_pool_top(self, attr_name, pd: PoolMapPair, title, no_pool_text, n_pools):
        top_pools = pd.get_top_pools(attr_name, n=n_pools)
        text = title + '\n'
        for i, pool in enumerate(top_pools, start=1):

            v = pd.get_value(pool.asset, attr_name)
            if attr_name == pd.BY_APY:
                v = f'{v:.1f}%'
            else:
                v = short_dollar(v)

            delta = pd.get_difference_percent(pool.asset, attr_name)
            # cut too small APY change
            if delta and abs(delta) < 1:
                delta = 0

            delta_p = bracketify(format_percent(delta, 100, signed=True)) if delta else ''

            asset = self.pretty_asset(pool.asset)

            text += f'{i}. {asset}: {v} {delta_p}\n'
        if not top_pools:
            text += no_pool_text
        return text.strip()

    def notification_text_best_pools(self, pd: PoolMapPair, n_pools):
        if pd.empty:
            return ''

        n_pools = 3  # less for Twitter
        text = '\n'.join([self.format_pool_top(top_pools, pd, title, '', n_pools)
                          for title, top_pools in [
                              ('💎 Best APY', pd.BY_APY),
                              ('💸 Top volume', pd.BY_VOLUME_24h),
                              ('🏊 Max Liquidity', pd.BY_DEPTH),
                          ]])
        return text

    def link_to_address(self, addr, name_map, chain=Chains.THOR):
        # without a link, just a caption
        name = name_map.by_address.get(addr)
        caption = add_thor_suffix(name) if name else short_address(addr, 0, 4)
        return f'[{caption}]'

    def notification_text_cex_flow(self, cex_flow: RuneCEXFlow):
        emoji = self.cex_flow_emoji(cex_flow)
        period_string = self.format_period(cex_flow.period_sec)
        return (
            f'🌬️ $Rune CEX flow last {period_string}\n'
            f'➡️ Inflow: {short_money(cex_flow.rune_cex_inflow, postfix=RAIDO_GLYPH)} '
            f'({short_dollar(cex_flow.in_usd)})\n'
            f'⬅️ Outflow: {short_money(cex_flow.rune_cex_outflow, postfix=RAIDO_GLYPH)} '
            f'({short_dollar(cex_flow.out_usd)})\n'
            f'{emoji} Netflow: {short_money(cex_flow.rune_cex_netflow, postfix=RAIDO_GLYPH, signed=True)} '
            f'({short_dollar(cex_flow.netflow_usd)})'
        )

    def notification_text_rune_transfer_public(self, t: RuneTransfer, name_map):
        asset, comment, from_my, to_my, tx_link, usd_amt, memo = self._native_transfer_prepare_stuff(
            None, t,
            tx_title='',
            name_map=name_map
        )

        asset = self.pretty_asset(asset)

        if t.memo:
            memo = f' (MEMO: "{shorten_text(t.memo, 21)}")'

        link = get_explorer_url_to_tx(self.cfg.network_id, Chains.THOR, t.tx_hash) if t and t.tx_hash else ''

        return (
            f'💸 Large transfer{comment}: '
            f'{short_money(t.amount)} {asset} {usd_amt} '
            f'from {from_my} ➡️ {to_my}{memo}\n'
            f'{link}'.strip()
        )

    # ----- SUPPLY ------

    SUPPLY_PIC_CAPTION = 'THORChain Rune supply chart'

    def format_supply_entry(self, name, s: SupplyEntry, total_of_total: int):
        locked_amount = sum(amount for _, amount in s.locked.items()) if s.locked else 0.0

        return (
            f'📍 {name}:\n'
            f'Free-fl.: {short_rune(s.circulating)} ({format_percent(s.circulating, total_of_total)})\n'
            f'Lock: {short_rune(locked_amount)} ({format_percent(locked_amount, total_of_total)})\n'
            f'Total: {short_rune(s.total)} ({format_percent(s.total, total_of_total)})\n\n'
        )

    def text_metrics_supply(self, market_info: RuneMarketInfo, killed_rune: KilledRuneEntry):
        parts = []
        supply = market_info.supply_info
        parts.append(self.format_supply_entry('BNB RUNE', supply.bep2_rune, supply.overall.total))
        parts.append(self.format_supply_entry('ETH RUNE', supply.erc20_rune, supply.overall.total))
        parts.append(self.format_supply_entry('Native Thor RUNE', supply.thor_rune, supply.overall.total))
        parts.append(self.format_supply_entry('Total RUNE', supply.overall, supply.overall.total))

        if killed_rune.block_id:
            switched_killed = short_rune(killed_rune.killed_switched)  # killed when switched
            total_killed = short_rune(killed_rune.total_killed)  # potentially dead + switched killed
            rune_left = short_rune(killed_rune.unkilled_unswitched_rune)
            parts.append(
                f'☠️ Killed-switched Rune: {switched_killed}\n'
                f'Total killed: {total_killed}\n'
                f'Unswitched left: {rune_left}\n\n'
            )

        return self.smart_split(parts)

    @staticmethod
    def format_dex_entry(e: DexReportEntry, r):
        n = e.count
        txs = 'tx' if n == 1 else 'txs'
        usd = e.rune_volume * r.usd_per_rune
        return (
            f'{n} {txs} | {short_rune(e.rune_volume)} | {short_dollar(usd)}'
        )

    def notification_text_dex_report(self, r: DexReport):
        period_str = self.format_period(r.period_sec)

        top_aggr = r.top_popular_aggregators()[:3]
        top_aggr_str = ''
        for i, (_, e) in enumerate(top_aggr, start=1):
            e: DexReportEntry
            top_aggr_str += f'{i}. {e.name}: {self.format_dex_entry(e, r)} \n'
        top_aggr_str = top_aggr_str or '-'

        top_asset_str = ''
        top_asset = r.top_popular_assets()[:3]
        for i, (_, e) in enumerate(top_asset, start=1):
            e: DexReportEntry
            top_asset_str += f'{i}. {e.name}: {self.format_dex_entry(e, r)} \n'
        top_asset_str = top_asset_str or '-'

        parts = [
            (
                f'🤹🏻‍ DEX aggregator last {period_str}\n\n'
                f'→ Swap In: {self.format_dex_entry(r.swap_ins, r)}\n'
                f'← Swap Out: {self.format_dex_entry(r.swap_outs, r)}\n'
                f'∑ Total: {self.format_dex_entry(r.total, r)}\n\n'
            ),
            f'Top DEX aggregators:\n{top_aggr_str}\n',
            f'Top DEX assets:\n{top_asset_str}'
        ]

        return self.smart_split(parts)

    def notification_text_saver_stats(self, event: EventSaverStats):
        parts = [f'💰 THORChain Savers\n']

        savers, prev = event.current_stats, event.previous_stats
        total_earned_usd = savers.total_rune_earned * event.price_holder.usd_per_rune
        avg_apr_change, saver_number_change, total_earned_change_usd, total_usd_change = \
            self.get_savers_stat_changed_metrics_as_str(event, prev, savers, total_earned_usd)
        fill_cap = savers.overall_fill_cap_percent(event.price_holder.pool_info_map)

        parts.append(
            f'\n'
            f'{savers.total_unique_savers}{saver_number_change} savers '
            f'| {(short_dollar(savers.total_usd_saved))}{total_usd_change}\n'
        )
        parts.append(
            f'Avg. APR is {(pretty_money(savers.average_apr))}%{avg_apr_change}\n'
        )
        parts.append(
            f'Earned: {pretty_dollar(total_earned_usd)}{total_earned_change_usd}\n'
        )
        parts.append(
            f'Total filled: {fill_cap:.1f}%\n\n'
        )

        return self.smart_split(parts)

    # ------ POL -------

    @staticmethod
    def pretty_asset(name):
        # we add '$' before assets to mention the asset name in Twitter
        return '$' + Asset(name).name

    def notification_text_pol_utilization(self, event: EventPOL):
        curr, prev = event.current, event.previous
        pol_progress = progressbar(curr.rune_withdrawn, event.mimir_max_deposit, 10)

        str_value_delta_pct, str_value_delta_abs = '', ''
        if prev:
            str_value_delta_pct = up_down_arrow(prev.rune_value, curr.rune_value, percent_delta=True, brackets=True,
                                                threshold_pct=0.5)
            # str_value_delta_abs = up_down_arrow(
            # prev.rune_value, curr.rune_value, money_delta=True, postfix=RAIDO_GLYPH)

        pnl_pct = curr.pnl_percent

        parts = [(
            f'🥃 Protocol Owned Liquidity\n\n'
            f"Current value: {short_rune(curr.rune_value)} or "
            f"{short_dollar(curr.usd_value)} {str_value_delta_pct}\n"
            f"Utilization: {pretty_percent(event.pol_utilization, signed=False)} {pol_progress} "
            f" of {short_rune(event.mimir_max_deposit)} maximum.\n"
            f"Rune deposited: {short_rune(curr.rune_deposited)}, "
            f"withdrawn: {short_rune(curr.rune_withdrawn)}\n"
            f"PnL: {pretty_percent(pnl_pct)} {chart_emoji(pnl_pct)}"
        )]

        # POL pool membership
        if event.membership:
            text = "\nPools:\n" + self._format_pol_membership(event, of_pool='of pool', decor=False)
            parts.append(text)

        return self.smart_split(parts)
