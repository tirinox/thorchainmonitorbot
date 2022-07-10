from typing import List

from aiothornode.types import ThorChainInfo
from semver import VersionInfo

from localization.base import BaseLocalization
from services.dialog.twitter.text_length import twitter_intelligent_text_splitter
from services.lib.constants import thor_to_float, rune_origin, BNB_RUNE_SYMBOL, Chains
from services.lib.date_utils import now_ts, seconds_human
from services.lib.money import Asset, short_dollar, format_percent, pretty_money, pretty_dollar, RAIDO_GLYPH, \
    calc_percent_change, adaptive_round_to_str, emoji_for_percent_change, short_address, short_money, short_rune
from services.lib.texts import x_ses, join_as_numbered_list, progressbar, plural, bracketify, up_down_arrow, \
    bracketify_spaced, shorten_text
from services.models.cap_info import ThorCapInfo
from services.models.last_block import EventBlockSpeed, BlockProduceState
from services.models.mimir import MimirChange, MimirHolder, MimirVoting, MimirVoteOption
from services.models.net_stats import NetworkStats
from services.models.node_info import NodeSetChanges, NodeVersionConsensus, NodeInfo
from services.models.pool_info import PoolDetailHolder, PoolChanges, PoolInfo
from services.models.price import RuneMarketInfo, PriceReport
from services.models.transfer import RuneCEXFlow, RuneTransfer
from services.models.tx import ThorTxExtended, ThorTxType
from services.notify.channel import MESSAGE_SEPARATOR


class TwitterEnglishLocalization(BaseLocalization):
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
    def tx_convert_string(tx: ThorTxExtended, usd_per_rune):
        inputs = tx.get_asset_summary(in_only=True)
        outputs = tx.get_asset_summary(out_only=True)

        input_str = ', '.join(f"{short_money(amount)} {asset}" for asset, amount in inputs.items())
        output_str = ', '.join(f"{short_money(amount)} {asset}" for asset, amount in outputs.items())

        return f"{input_str} ➡️ {output_str} ({short_dollar(tx.get_usd_volume(usd_per_rune))})"

    def notification_text_large_single_tx(self, tx: ThorTxExtended, usd_per_rune: float,
                                          pool_info: PoolInfo,
                                          cap: ThorCapInfo = None):
        (ap, asset_side_usd_short, chain, percent_of_pool, pool_depth_usd, rp, rune_side_usd_short,
         total_usd_volume) = self.lp_tx_calculations(usd_per_rune, pool_info, tx)

        heading = ''
        if tx.type == ThorTxType.TYPE_ADD_LIQUIDITY:
            heading = f'🐳 Add liquidity 🟢'
        elif tx.type == ThorTxType.TYPE_WITHDRAW:
            heading = f'🐳 Withdraw liquidity 🔴'
        elif tx.type == ThorTxType.TYPE_DONATE:
            heading = f'🙌 Donation to the pool'
        elif tx.type == ThorTxType.TYPE_SWAP:
            heading = f'🐳 Swap 🔁'
        elif tx.type == ThorTxType.TYPE_REFUND:
            heading = f'🐳 Refund ↩️❗'
        elif tx.type == ThorTxType.TYPE_SWITCH:
            heading = f'🐳 Rune switch 🆙'

        asset = Asset(tx.first_pool).name

        content = ''
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
                ilp_rune_fmt = short_rune(ilp_rune)
                ilp_text = f'🛡️ IL prot. paid: {ilp_rune_fmt} ' \
                           f'({short_dollar(ilp_rune * usd_per_rune)})\n'
            else:
                ilp_text = ''

            content = (
                f"{short_money(tx.rune_amount)} {self.R} ({rp:.0f}% = {rune_side_usd_short}) ↔️ "
                f"{short_money(tx.asset_amount)} {asset} "
                f"({ap:.0f}% = {asset_side_usd_short})\n"
                f"Total: {short_dollar(total_usd_volume)} ({percent_of_pool:.2f}% of pool).\n"
                f"{aff_text}"
                f"{ilp_text}"
                f"The depth is {short_dollar(pool_depth_usd)} now."
            )
        elif tx.type == ThorTxType.TYPE_SWITCH:
            # [Amt] Rune [Blockchain: ERC20/BEP2] -> [Amt] THOR Rune ($usd)
            if tx.first_input_tx and tx.first_output_tx:
                amt = thor_to_float(tx.first_input_tx.first_amount)
                origin = rune_origin(tx.first_input_tx.first_asset)
                content = (
                    f"{short_money(amt)} {origin} {self.R} ➡️ {short_money(amt)} Native {self.R} "
                    f"({short_dollar(tx.get_usd_volume(usd_per_rune))})"
                )
        elif tx.type == ThorTxType.TYPE_REFUND:
            reason = shorten_text(tx.meta_refund.reason, 30)
            content = (
                    self.tx_convert_string(tx, usd_per_rune) +
                    f"\nReason: {reason}.."
            )
        elif tx.type == ThorTxType.TYPE_SWAP:
            content = self.tx_convert_string(tx, usd_per_rune)
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

        msg = f"{heading}\n{content}"

        if cap:
            msg += (
                f"\n\n"
                f"Liq. cap is {format_percent(cap.pooled_rune, cap.cap)} full now.\n"
                f'You can add {short_money(cap.how_much_rune_you_can_lp)} {self.R} '
                f'({short_dollar(cap.how_much_usd_you_can_lp)}) more.\n'
            )

        return msg.strip()

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
            return f'  • {Asset(pool_name).short_str}: {extra}'

        if pc.pools_added:
            message += '✅ Pools added:\n' + '\n'.join([pool_text(*a) for a in pc.pools_added]) + '\n'
        if pc.pools_removed:
            message += ('❌ Pools removed:\n' + '\n'.join([pool_text(*a, can_swap=False) for a in pc.pools_removed])
                        + '\n')
        if pc.pools_changed:
            message += '🔄 Pools changed:\n' + '\n'.join([pool_text(*a) for a in pc.pools_changed]) + '\n'

        return message.rstrip()

    def notification_text_network_summary(self, old: NetworkStats, new: NetworkStats, market: RuneMarketInfo):
        parts = []

        message = '🌐 THORChain stats\n'

        security_text = self.network_bond_security_text(new.network_security_ratio)
        message += f'Network is {security_text}.\n'

        active_nodes_change = bracketify_spaced(up_down_arrow(old.active_nodes, new.active_nodes, int_delta=True))
        standby_nodes_change = bracketify_spaced(up_down_arrow(old.active_nodes, new.active_nodes, int_delta=True))
        message += f"{new.active_nodes} active nodes{active_nodes_change}" \
                   f"and {new.standby_nodes} standby nodes{standby_nodes_change}\n"

        parts.append(message)
        message = ''

        # -- BOND

        current_bond_text = short_rune(new.total_active_bond_rune)
        current_bond_change = bracketify(
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

        message = f"🔗 Active bond: {current_bond_text}{current_bond_change} or " \
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

        message = f'🛡 Total Imp. Loss. Protection paid: {(short_dollar(new.loss_protection_paid_usd))}.\n'
        parts.append(message)


        # --------------------------------------------------------------------------------------------------------------

        switch_rune_total_text = short_rune(new.switched_rune)
        message = (
            f'💎 Total Rune switched to native: {switch_rune_total_text} '
            f'({format_percent(new.switched_rune, market.total_supply)})\n'
        )

        bonding_apy_change, liquidity_apy_change = self._extract_apy_deltas(new, old)

        message += (
            f'📈 Bonding APY is {pretty_money(new.bonding_apy, postfix="%")}{bonding_apy_change} and '
            f'Liquidity APY is {pretty_money(new.liquidity_apy, postfix="%")}{liquidity_apy_change}.\n'
        )

        parts.append(message)

        if new.users_daily or new.users_monthly:
            daily_users_change = bracketify(up_down_arrow(old.users_daily, new.users_daily, int_delta=True))
            monthly_users_change = bracketify(up_down_arrow(old.users_monthly, new.users_monthly, int_delta=True))
            message = f'👥 Daily users: {new.users_daily}{daily_users_change}, ' \
                      f'monthly users: {new.users_monthly}{monthly_users_change}\n'
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

        return MESSAGE_SEPARATOR.join(twitter_intelligent_text_splitter(parts))

    @staticmethod
    def _format_node_text_plain(node: NodeInfo, with_ip):
        node_ip_link = bracketify(node.ip_address or 'no IP') if with_ip else ''
        node_thor_link = short_address(node.node_address, 0)
        return f'{node_thor_link} {node_ip_link} ' \
               f'bond {short_money(node.bond, postfix=RAIDO_GLYPH)}'

    def _make_node_list_plain(self, nodes, title, start=1, with_ip=True):
        if not nodes:
            return ''

        message = title + "\n"
        message += join_as_numbered_list(
            (self._format_node_text_plain(node, with_ip) for node in nodes if node.node_address),
            start=start
        )
        return message + "\n"

    def _node_bond_change_after_churn(self, changes: NodeSetChanges):
        bond_in, bond_out = changes.bond_churn_in, changes.bond_churn_out
        bond_delta = bond_in - bond_out
        return f'Active bond net change: {short_money(bond_delta, postfix=RAIDO_GLYPH)}'

    def notification_text_for_node_churn(self, changes: NodeSetChanges):
        components = []

        part1 = ''
        if changes.nodes_activated or changes.nodes_deactivated:
            part1 += '♻️ Node churn' + '\n'
        part1 += self._make_node_list_plain(changes.nodes_activated, '➡️ Nodes churned in:',
                                            with_ip=(len(changes.nodes_activated) <= 4))
        components.append(part1)

        part2 = self._make_node_list_plain(changes.nodes_deactivated, '⬅️️ Nodes churned out:',
                                           with_ip=(len(changes.nodes_deactivated) <= 4))
        if changes.nodes_activated or changes.nodes_deactivated:
            part2 += self._node_bond_change_after_churn(changes)
        components.append(part2)

        part3 = self._make_node_list_plain(changes.nodes_added, '🆕 New nodes:',
                                           with_ip=(len(changes.nodes_added) <= 4))
        components.append(part3)

        part4 = self._make_node_list_plain(changes.nodes_removed, '🗑️ Nodes disconnected:',
                                           with_ip=(len(changes.nodes_removed) <= 4))

        components.append(part4)

        return MESSAGE_SEPARATOR.join(twitter_intelligent_text_splitter(components))

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

    def notification_text_mimir_voting_progress(self, holder: MimirHolder, key, prev_progress, voting: MimirVoting,
                                                option: MimirVoteOption):
        message = '🏛️ Node-Mimir voting update\n'

        name = holder.pretty_name(key)
        message += f"{name}\n"

        pb = self.make_voting_progress_bar(option, voting)
        extra = self._text_votes_to_pass(option)
        message += f" to set it ➔ {option.value}: " \
                   f"{format_percent(option.number_votes, voting.active_nodes)}" \
                   f" ({option.number_votes}/{voting.active_nodes}) {pb} {extra}\n"
        return message

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
            old_value_fmt = self.format_mimir_value(change.old_value, change.entry)
            new_value_fmt = self.format_mimir_value(change.new_value, change.entry)
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

    def format_pool_top(self, attr_name, pd: PoolDetailHolder, title, no_pool_text, n_pools):
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

            asset = Asset.from_string(pool.asset).shortest

            text += f'{i}. {asset}: {v} {delta_p}\n'
        if not top_pools:
            text += no_pool_text
        return text.strip()

    def notification_text_best_pools(self, pd: PoolDetailHolder, n_pools):
        n_pools = 3  # less for Twitter
        no_pool_text = 'Nothing yet. Maybe still loading...'
        text = '\n'.join([self.format_pool_top(top_pools, pd, title, no_pool_text, n_pools) for title, top_pools in [
            ('💎 Best APY', pd.BY_APY),
            ('💸 Top volume', pd.BY_VOLUME_24h),
            ('🏊 Max Liquidity', pd.BY_DEPTH),
        ]])
        return text

    def link_to_address(self, addr, chain=Chains.THOR):
        name = self.name_service.lookup_name_by_address_local(addr)
        # without a link, just a caption
        return name.name if name else short_address(addr)

    def notification_text_bep2_movement(self, transfer: RuneTransfer):
        from_link, to_link = self.link_to_address(transfer.from_addr), self.link_to_address(transfer.to_addr)
        pf = ' ' + BNB_RUNE_SYMBOL
        return (f'{RAIDO_GLYPH} Large BEP2 $Rune transfer\n'
                f'{short_money(transfer.amount, postfix=pf)} ({short_dollar(transfer.usd_amount)}) '
                f'from {from_link} ➡️ to {to_link}.')

    def notification_text_cex_flow(self, bep2flow: RuneCEXFlow):
        return (
            f'🌬️ BEP2.Rune CEX flow last 24 hours\n'
            f'Inflow: {short_money(bep2flow.rune_cex_inflow, postfix=RAIDO_GLYPH)} '
            f'({short_dollar(bep2flow.in_usd)})\n'
            f'Outflow: {short_money(bep2flow.rune_cex_outflow, postfix=RAIDO_GLYPH)} '
            f'({short_dollar(bep2flow.out_usd)})\n'
            f'Netflow: {short_money(bep2flow.rune_cex_netflow, postfix=RAIDO_GLYPH)} '
            f'({short_dollar(bep2flow.netflow_usd)})'
        )

    def notification_text_rune_transfer_public(self, t: RuneTransfer):
        asset, comment, from_my, to_my, tx_link, usd_amt = self._native_transfer_prepare_stuff(None, t, tx_title='')

        return f'💸 Large transfer {comment}: ' \
               f'{(short_money(t.amount, postfix=" " + asset))} {usd_amt} ' \
               f'from {from_my} ➡️ {to_my}.'
