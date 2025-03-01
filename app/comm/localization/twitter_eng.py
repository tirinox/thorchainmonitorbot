from typing import List

from api.aionode.types import ThorChainInfo
from api.midgard.name_service import NameMap, add_thor_suffix
from api.w3.dex_analytics import DexReportEntry, DexReport
from comm.twitter.text_length import twitter_intelligent_text_splitter, TWITTER_LIMIT_CHARACTERS
from jobs.fetch.chain_id import AlertChainIdChange
from lib.config import Config
from lib.constants import Chains, BTC_SYMBOL, ETH_SYMBOL
from lib.date_utils import now_ts, seconds_human
from lib.explorers import get_explorer_url_to_tx
from lib.money import short_dollar, format_percent, pretty_money, pretty_dollar, RAIDO_GLYPH, \
    calc_percent_change, adaptive_round_to_str, emoji_for_percent_change, short_address, short_money, short_rune, \
    pretty_percent, chart_emoji, pretty_rune
from lib.texts import x_ses, progressbar, plural, bracketify, up_down_arrow, \
    bracketify_spaced, shorten_text
from models.asset import Asset
from models.cap_info import ThorCapInfo
from models.circ_supply import EventRuneBurn
from models.key_stats_model import AlertKeyStats
from models.last_block import EventBlockSpeed, BlockProduceState
from models.loans import AlertLoanOpen, AlertLoanRepayment, AlertLendingStats, AlertLendingOpenUpdate
from models.memo import ActionType
from models.mimir import MimirChange, MimirHolder
from models.net_stats import AlertNetworkStats
from models.node_info import NodeSetChanges, NodeInfo
from models.pool_info import EventPools, PoolChanges, PoolInfo
from models.price import RuneMarketInfo, AlertPrice, AlertPriceDiverge
from models.runepool import AlertPOLState, AlertRunePoolAction, AlertRunepoolStats
from models.s_swap import AlertSwapStart
from models.savers import AlertSaverStats
from models.trade_acc import AlertTradeAccountAction, AlertTradeAccountStats
from models.transfer import RuneCEXFlow, RuneTransfer
from models.tx import EventLargeTransaction
from models.version import AlertVersionUpgradeProgress, AlertVersionChanged
from notify.channel import MESSAGE_SEPARATOR
from .achievements.ach_tw_eng import AchievementsTwitterEnglishLocalization
from .eng_base import BaseLocalization


class TwitterEnglishLocalization(BaseLocalization):
    def __init__(self, cfg: Config):
        super().__init__(cfg)
        self.ach = AchievementsTwitterEnglishLocalization()
        self.twitter_max_len = cfg.get('twitter.max_length', TWITTER_LIMIT_CHARACTERS)

    TEXT_DECORATION_ENABLED = False

    def smart_split(self, parts):
        parts = twitter_intelligent_text_splitter(parts, self.twitter_max_len)
        return MESSAGE_SEPARATOR.join(parts).strip()

    def link_to_tx(self, tx_id, chain=Chains.THOR, label="TX"):
        return "TX: " + get_explorer_url_to_tx(self.cfg.network_id, chain, tx_id)

    PIC_NODE_DIVERSITY_BY_PROVIDER_CAPTION = 'THORChain nodes'

    def notification_text_cap_change(self, old: ThorCapInfo, new: ThorCapInfo):
        up = old.cap < new.cap
        verb = "has been increased" if up else "has been decreased"
        arrow = '⬆️' if up else '⚠️ ⬇️'
        message = (
            f'{arrow} Pool cap {verb} from {short_money(old.cap)} to {short_money(new.cap)}!\n'
            f'Currently {short_money(new.pooled_rune)} {self.R} are in the liquidity pools.\n'
            f'{self._cap_progress_bar(new)}\n'
            f'{self.can_add_more_lp_text(new)}\n'
            f'The price of {self.R} in the pools is ${new.price:.3f}.'
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
            f'{short_money(cap.cap)} {self.R} max pooled ({format_percent(cap.pooled_rune, cap.cap)})\n'
            f'{self.can_add_more_lp_text(cap)}'
        )

    @staticmethod
    def format_op_amount(amt):
        return short_money(amt)

    def notification_text_large_single_tx(self, e: EventLargeTransaction, name_map: NameMap):
        usd_per_rune, pool_info, tx = e.usd_per_rune, e.pool_info, e.transaction

        (ap, asset_side_usd_short, chain, percent_of_pool, pool_depth_usd, rp, rune_side_usd_short,
         total_usd_volume) = self.lp_tx_calculations(usd_per_rune, pool_info, tx)

        heading = ''
        if tx.is_of_type(ActionType.ADD_LIQUIDITY):
            if tx.is_savings:
                heading = f'🐳→💰 Add to savings vault'
            else:
                heading = f'🐳→⚡ Add liquidity'
        elif tx.is_of_type(ActionType.WITHDRAW):
            if tx.is_savings:
                heading = f'🐳←💰 Withdraw from savings vault'
            else:
                heading = f'🐳←⚡ Withdraw liquidity'
        elif tx.is_of_type(ActionType.DONATE):
            heading = f'🐳 Donation to the pool 🙌'
        elif tx.is_of_type(ActionType.SWAP):
            if tx.is_streaming:
                heading = f'🌊 Streaming swap finished'
            else:
                heading = f'🔁 Swap'
        elif tx.is_of_type(ActionType.REFUND):
            heading = f'🐳 Refund ↩️❗'

        if tx.is_pending:
            heading += ' [Pending]'

        # it is old
        if date_text := self.tx_date(tx):
            heading += f' {date_text}'

        content = f'👤{self.link_to_address(tx.sender_address, name_map)}: '

        if tx.is_of_type((ActionType.ADD_LIQUIDITY, ActionType.WITHDRAW, ActionType.DONATE)):
            if tx.affiliate_fee > 0:
                aff_text = f'Aff. fee: {format_percent(tx.affiliate_fee, 1)}\n'
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

            asset = self.pretty_asset(tx.first_pool)

            if tx.is_savings:
                rune_part = ''
                asset_part = f"{short_money(tx.asset_amount)} {asset}"
                amount_more, asset_more, saver_pb, saver_cap, saver_percent = \
                    self.get_savers_limits(pool_info, usd_per_rune, e.mimir, tx.asset_amount)
                pool_depth_part = f'Savers cap is {saver_pb} full. '

                if self.show_add_more and amount_more > 0:
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

        elif tx.is_of_type(ActionType.REFUND):
            reason = shorten_text(tx.meta_refund.reason, 30)
            content += (
                    self.format_swap_route(tx, usd_per_rune) +
                    f"\nReason: {reason}.."
            )
        elif tx.is_of_type(ActionType.SWAP):
            content += self.format_swap_route(tx, usd_per_rune)

            if tx.is_streaming:
                if (success := tx.meta_swap.streaming.success_rate) < 1.0:
                    good = tx.meta_swap.streaming.successful_swaps
                    total = tx.meta_swap.streaming.quantity
                    content += f'\nSuccess rate: {format_percent(success, 1)} ({good}/{total})'


        link = get_explorer_url_to_tx(self.cfg.network_id, Chains.THOR, tx.first_input_tx_hash) \
            if tx and tx.tx_hash else ''

        msg = f"{heading}\n" \
              f"{content}\n" \
              f"Runescan: {link}"

        return msg.strip()

    def notification_text_streaming_swap_started(self, e: AlertSwapStart, name_map: NameMap):
        user_link = self.link_to_address(e.from_address, name_map)

        tx_link = self.url_for_tx_tracker(e.tx_id)
        asset_str = Asset(e.in_asset).pretty_str
        amount_str = self.format_op_amount(e.in_amount_float)
        target_asset_str = Asset(e.out_asset).pretty_str

        runescan_link = get_explorer_url_to_tx(self.cfg.network_id, Chains.THOR, e.tx_id)

        return (
            f'🌊 New streaming swap\n'
            f'{user_link}: {amount_str} {asset_str} ({short_dollar(e.volume_usd)}) → ⚡ → {target_asset_str}\n'
            f'Track Tx: {tx_link}.\n'
            f'Runescan: {runescan_link}'
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

    def notification_text_price_update(self, p: AlertPrice):
        message = '🚀 New all-time high!\n' if p.is_ath else ''

        price = p.market_info.pool_rune_price

        btc_price = f"₿ {p.btc_pool_rune_price:.8f}"
        message += f"$RUNE price is now ${price:.3f} ({btc_price}).\n"

        c_gecko_url = 'https://www.coingecko.com/en/coins/thorchain'
        message += f"Coingecko: {c_gecko_url}\n"

        return message.rstrip()

    def notification_text_price_divergence(self, e: AlertPriceDiverge):
        title = f'〰️ Low {self.R} price divergence!' if e.below_min_divergence else f'🔺 High {self.R} price divergence!'

        div, div_p = e.info.divergence_abs, e.info.divergence_percent
        exclamation = self._exclamation_sign(div_p, ref=10)

        text = (
            f"🖖 {title}\n"
            f"CEX Rune price is {pretty_dollar(e.info.cex_price)}\n"
            f"Weighted average Rune price over liquidity pools is {pretty_dollar(e.info.pool_rune_price)}\n"
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

    def notification_text_network_summary(self, e: AlertNetworkStats):
        new, old, nodes = e.new, e.old, e.nodes

        parts = []

        message = '🌐 THORChain stats\n'

        def flush():
            nonlocal message
            parts.append(message)
            message = ''

        # --------------- NODES / SECURITY --------------------

        sec_ratio = self.get_network_security_ratio(new, nodes)
        if sec_ratio > 0:
            security_text = self.network_bond_security_text(sec_ratio)
            message += f'Network is now {security_text}.\n'

        active_nodes_change = bracketify_spaced(up_down_arrow(old.active_nodes, new.active_nodes, int_delta=True))
        standby_nodes_change = bracketify_spaced(up_down_arrow(old.active_nodes, new.active_nodes, int_delta=True))
        message += f"{new.active_nodes} active nodes{active_nodes_change}" \
                   f" and {new.standby_nodes} standby nodes{standby_nodes_change}\n"

        flush()

        # --------------- NODE BOND --------------------

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

        message += f"🔗 Active bond: {current_active_bond_text}{current_active_bond_change} or " \
                   f"{current_bond_usd_text}{current_bond_usd_change}.\n"

        message += f"Total bond: {current_total_bond_text}{current_total_bond_change} or " \
                   f"{current_total_bond_usd_text}{current_total_bond_usd_change}.\n"

        flush()

        # --------------- POOLED RUNE --------------------

        # current_pooled_text = short_rune(new.total_rune_lp)
        # current_pooled_change = bracketify(
        #     up_down_arrow(old.total_rune_lp, new.total_rune_lp, money_delta=True))

        current_pooled_usd_text = short_dollar(new.total_pooled_usd)
        current_pooled_usd_change = bracketify(
            up_down_arrow(old.total_pooled_usd, new.total_pooled_usd, money_delta=True, money_prefix='$'))

        message += f"🏊 Total pooled: {current_pooled_usd_text}{current_pooled_usd_change}.\n"

        current_liquidity_usd_text = short_dollar(new.total_liquidity_usd)
        current_liquidity_usd_change = bracketify(
            up_down_arrow(old.total_liquidity_usd, new.total_liquidity_usd, money_delta=True, money_prefix='$'))

        message += f"🌊 Total liquidity (TVL): {current_liquidity_usd_text}{current_liquidity_usd_change}.\n"

        # ----------------- LIQUIDITY / BOND / RESERVE --------------------------------

        tlv_change = bracketify(
            up_down_arrow(old.total_locked_usd, new.total_locked_usd, money_delta=True, money_prefix='$'))
        message += f'🏦 TVL + Bond: {short_dollar(new.total_locked_usd)}{tlv_change}.\n'
        flush()

        # ----------------- ADD/WITHDRAW STATS -----------------

        message += f'Last 24 hours:\n'

        price = new.usd_per_rune

        if old.is_ok:
            # 24 h Add/withdrawal
            added_24h_rune = new.added_rune - old.added_rune
            withdrawn_24h_rune = new.withdrawn_rune - old.withdrawn_rune

            add_rune_text = short_rune(added_24h_rune)
            withdraw_rune_text = short_rune(withdrawn_24h_rune)

            add_usd_text = short_dollar(added_24h_rune * price)
            withdraw_usd_text = short_dollar(withdrawn_24h_rune * price)

            if added_24h_rune:
                message += f'➕ Rune added to pools: {add_rune_text} ({add_usd_text}).\n'

            if withdrawn_24h_rune:
                message += f'➖ Rune withdrawn: {withdraw_rune_text} ({withdraw_usd_text}).\n'

        # ----------------- SWAPS STATS -----------------

        # synth_volume_usd = short_dollar(new.synth_volume_24h_usd)
        # synth_op_count = short_money(new.synth_op_count)

        trade_volume_usd = short_dollar(new.trade_volume_24h_usd)
        trade_op_count = short_money(new.trade_op_count)

        swap_usd_text = short_dollar(new.swap_volume_24h_usd)
        swap_op_count = short_money(new.swaps_24h)

        message += f'🔀 Total swap volume: {swap_usd_text} in {swap_op_count} operations.\n'
        message += f'🆕 Trade asset volume {trade_volume_usd} in {trade_op_count} swaps.\n'
        flush()

        # ---------------- APY -----------------

        bonding_apy_change, liquidity_apy_change = self._extract_apy_deltas(new, old)

        message += (
            f'📈 Bonding APY is {pretty_money(new.bonding_apy, postfix="%")}{bonding_apy_change}.\n'
        )
        message += (
            f'Liquidity APY is {pretty_money(new.liquidity_apy, postfix="%")}{liquidity_apy_change}.\n'
        )

        if new.users_daily or new.users_monthly:
            daily_users_change = bracketify(up_down_arrow(old.users_daily, new.users_daily, int_delta=True))
            monthly_users_change = bracketify(up_down_arrow(old.users_monthly, new.users_monthly, int_delta=True))
            message += f'👥 Daily users: {new.users_daily}{daily_users_change},' \
                       f' monthly users: {new.users_monthly}{monthly_users_change} 🆕\n'

        flush()

        return self.smart_split(parts)

    def _node_bond_change_after_churn(self, changes: NodeSetChanges):
        bond_in, bond_out = changes.bond_churn_in, changes.bond_churn_out
        bond_delta = bond_in - bond_out
        return f'Active bond net change: {short_money(bond_delta, postfix=RAIDO_GLYPH, signed=True)}'

    def notification_text_node_churn_finish(self, changes: NodeSetChanges):
        def _format_node_text_plain(node: NodeInfo):
            node_thor_link = short_address(node.node_address, 0)
            return f'{node.flag_emoji}{node_thor_link} ({short_money(node.bond, postfix=RAIDO_GLYPH)})'

        def _make_node_list_plain(nodes, title):
            if not nodes:
                return ''
            message = ', '.join(_format_node_text_plain(node) for node in nodes if node.node_address)
            return f'{title}\n{message}\n\n'

        components = [
            '♻️ Node churn is complete\n\n'
        ]

        part1 = _make_node_list_plain(changes.nodes_activated, '➡️ Churned in:')
        components.append(part1)

        part2 = _make_node_list_plain(changes.nodes_deactivated, '⬅️️ Churned out:')

        # bond
        if changes.nodes_activated or changes.nodes_deactivated:
            part2 += self._node_bond_change_after_churn(changes)
        components.append(part2)

        if changes.churn_duration:
            components.append(
                f'\nChurn duration: {seconds_human(changes.churn_duration)}'
            )

        part3 = _make_node_list_plain(changes.nodes_added, '🆕 New nodes:')
        components.append(part3)

        part4 = _make_node_list_plain(changes.nodes_removed, '🗑️ Nodes disconnected:')
        components.append(part4)

        return self.smart_split(components)

    def notification_churn_started(self, changes: NodeSetChanges):
        text = f'♻️ Node churn have started at block #{changes.block_no}'
        if changes.vault_migrating:
            text += '\nVaults are migrating.'
        return text

    @staticmethod
    def node_version(v, data: NodeSetChanges, active=True):
        realm = data.active_only_nodes if active else data.nodes_all
        n_nodes = len(data.find_nodes_with_version(realm, v))
        return f"{v} ({n_nodes} {plural(n_nodes, 'node', 'nodes')})"

    def notification_text_version_changed_progress(self, e: AlertVersionUpgradeProgress):
        msg = '🕖 Version upgrade progress\n'

        progress = e.ver_con.ratio * 100.0
        pb = progressbar(progress, 100.0, 14)

        msg += f'{pb} {progress:.0f} %\n'
        msg += f"{e.ver_con.top_version_count} of {e.ver_con.total_active_node_count} nodes " \
               f"upgraded to version {e.ver_con.top_version}.\n"

        cur_version_txt = self.node_version(e.data.current_active_version, e.data)
        msg += f"⚡️ Active protocol version is {cur_version_txt}.\n" + \
               '* Minimum version among all active nodes.'

        return msg

    def notification_text_version_changed(self, e: AlertVersionChanged):
        msg = '💫 THORChain protocol version update\n'

        def version_and_nodes(v, nodes_all=False):
            realm = e.data.nodes_all if nodes_all else e.data.active_only_nodes
            n_nodes = len(e.data.find_nodes_with_version(realm, v))
            return f"{v} ({n_nodes} {plural(n_nodes, 'node', 'nodes')})"

        current_active_version = e.data.current_active_version

        if e.new_versions:
            new_version_joined = ', '.join(version_and_nodes(v, nodes_all=True) for v in e.new_versions)
            msg += f"🆕 New version detected: {new_version_joined}\n"

            msg += f"⚡️ Active protocol version is {version_and_nodes(current_active_version)}\n" + \
                   '* Minimum version among all active nodes.\n'

        if e.old_active_ver != e.new_active_ver:
            action = 'upgraded' if e.new_active_ver > e.old_active_ver else 'downgraded'
            emoji = '🆙' if e.new_active_ver > e.old_active_ver else '⬇️'
            msg += (
                f"{emoji} Attention! Active protocol version has been {action} "
                f"from {e.old_active_ver} to {version_and_nodes(e.new_active_ver)}\n"
            )

            cnt = e.data.version_counter(e.data.active_only_nodes)
            if len(cnt) == 1:
                msg += f"All active nodes run version {current_active_version}\n"
            elif len(cnt) > 1:
                msg += f"The most popular versions are\n"
                for i, (v, count) in enumerate(cnt.most_common(5), start=1):
                    active_node = ' 👈' if v == current_active_version else ''
                    msg += f"{i}. {version_and_nodes(v)} {active_node}\n"
                msg += f"Maximum version available is {version_and_nodes(e.data.max_available_version)}\n"

        return msg

    TEXT_MIMIR_VOTING_PROGRESS_TITLE = '🏛 Node-Mimir voting update\n\n'

    def notification_text_trading_halted_multi(self, chain_infos: List[ThorChainInfo]):
        msg = ''

        halted_chains = ', '.join(c.chain for c in chain_infos if c.halted)
        if halted_chains:
            msg += f'🚨 Attention! Trading is halted on the {halted_chains} chain! ' \
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

    LEND_DICT = {
        BTC_SYMBOL: "₿ $BTC",
        ETH_SYMBOL: "Ξ $ETH",
    }

    def notification_text_mimir_changed(self, changes: List[MimirChange], mimir: MimirHolder):
        if not changes:
            return ''

        text = '🔔 Mimir update!\n\n'

        for change in changes:
            old_value_fmt, new_value_fmt = self._old_and_new_mimir(change, mimir)

            name = f'{change.entry.pretty_name} ({change.entry.name})' if change.entry else change.name

            e = change.entry
            if e:
                if e.source == e.SOURCE_AUTO:
                    text += '[🤖 Auto-solvency ]  '
                elif e.source == e.SOURCE_ADMIN:
                    pass
                    # text += '[👩‍💻 Admins ]  '
                elif e.source == e.SOURCE_NODE:
                    text += '[🤝 Nodes voted ]  '
                elif e.source == e.SOURCE_NODE_PAUSE:
                    text += '[⏸️] '
                elif e.source == e.SOURCE_NODE_CEASED:
                    text += '[💔 Node-Mimir off ]  '

            if change.kind == MimirChange.ADDED_MIMIR:
                text += (
                    f'➕ New Mimir \"{name}\". '
                    f'Default: {old_value_fmt} → New: {new_value_fmt}'
                )
            elif change.kind == MimirChange.REMOVED_MIMIR:
                text += f"➖ Mimir \"{name}\" has been removed. It was {old_value_fmt} before."
                if change.new_value is not None:
                    text += f" Now it has its default value: {new_value_fmt}."
            else:
                text += (
                    f"\"{name}\": {old_value_fmt} → {new_value_fmt}️"
                )
                if change.entry.automatic and change.non_zero_value:
                    text += f' at block #{change.new_value}.'
            text += '\n'

        return text.strip()

    def format_pool_top(self, attr_name, pd: EventPools, title, no_pool_text, n_pools):
        top_pools = pd.get_top_pools(attr_name, n=n_pools)
        text = title + '\n'
        for i, pool in enumerate(top_pools, start=1):

            v = pd.get_value(pool.asset, attr_name)
            if attr_name == pd.BY_APR:
                v = f'{v:.1f}%'
            else:
                v = short_dollar(v)

            delta = pd.get_difference_percent(pool.asset, attr_name)
            # cut too small APY change
            if delta and abs(delta) < 1:
                delta = 0

            try:
                delta_p = bracketify(pretty_money(delta, signed=True, postfix=' pp')) if delta else ''
            except ValueError:
                delta_p = ''

            # delta_p = bracketify(format_percent(delta, 100, signed=True)) if delta else ''

            asset = self.pretty_asset(pool.asset)

            text += f'{i}. {asset}: {v} {delta_p}\n'
        if not top_pools:
            text += no_pool_text
        return text.strip()

    def notification_text_best_pools(self, pd: EventPools, n_pools):
        return 'THORChain top liquidity pools'

    def link_to_address(self, addr, name_map, chain=Chains.THOR, is_loan=False):
        # without a link, just a caption
        if name_map:
            name = name_map.by_address.get(addr)
        else:
            name = None
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

    def notification_text_rune_transfer_public(self, t: RuneTransfer, name_map: NameMap):
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

    def text_metrics_supply(self, market_info: RuneMarketInfo):
        sp = market_info.supply_info

        burn_amt = short_rune(abs(sp.total_burned_rune))
        burn_pct = format_percent(abs(sp.total_burned_rune), sp.total)

        return (
            f'⚡️ Rune supply is {pretty_rune(market_info.total_supply)}.\n'
            f'🔥 Burned Rune: {burn_amt} ({burn_pct})\n'
            f'🏊‍ Liquidity pools: {short_rune(sp.pooled)} ({format_percent(sp.pooled_percent)})\n'
            f'🏊‍♀️ RUNEPool: {short_rune(sp.runepool)} ({format_percent(sp.runepool_percent)})\n'
            f'⚡️ POL: {short_rune(sp.pol)} ({format_percent(sp.pol_percent)})\n'
            f'🔒 Bond: {short_rune(sp.bonded)} ({format_percent(sp.bonded_percent)})\n'
            f'🏦 CEX: {short_rune(sp.in_cex)} ({format_percent(sp.in_cex_percent, )})\n'
            f'💰 Treasury: {short_rune(sp.treasury)}'
        )

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

    def notification_text_saver_stats(self, event: AlertSaverStats):
        parts = [f'💰 THORChain Savers\n']

        savers, prev = event.current_stats, event.previous_stats
        total_earned_usd = savers.total_rune_earned * event.usd_per_rune
        avg_apr_change, saver_number_change, total_earned_change_usd, total_usd_change = \
            self.get_savers_stat_changed_metrics_as_str(event, prev, savers, total_earned_usd)
        fill_cap = savers.overall_fill_cap_percent(event.pool_map)

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
    def pretty_asset(name, abbr=True):
        if not name:
            return '???'

        asset = Asset(name.upper())
        synth = 'synth ' if asset.is_synth else ('tr. ' if asset.is_trade else '')

        if asset.name == asset.chain and not asset.tag:
            chain = ''
        elif 'USD' in asset.name or 'BNB' in asset.name:
            chain = f' ({asset.chain})'
        else:
            chain = ''

        # we add '$' before assets to mention the asset name in Twitter
        return f'{synth}${asset.name}{chain}'

    def notification_text_pol_stats(self, event: AlertPOLState):
        curr, prev = event.current, event.previous
        pol_progress = progressbar(curr.rune_value, event.mimir_max_deposit, 10)

        str_value_delta_pct, str_value_delta_abs = '', ''
        if prev:
            str_value_delta_pct = up_down_arrow(prev.rune_value, curr.rune_value, percent_delta=True, brackets=True,
                                                threshold_pct=0.5)
            # str_value_delta_abs = up_down_arrow(
            # prev.rune_value, curr.rune_value, money_delta=True, postfix=RAIDO_GLYPH)

        pnl_pct = curr.pnl_percent

        parts = [(
            f'🥃 Protocol Owned Liquidity\n'
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
            text = "\n🥃 POL pool membership:\n" + self._format_pol_membership(event, of_pool='of pool', decor=False)
            parts.append(text)

        return self.smart_split(parts)

    def notification_text_key_metrics_caption(self, data: AlertKeyStats):
        return '.@THORChain weekly stats $RUNE'

    # ----- LOANS ------

    def notification_text_loan_open(self, event: AlertLoanOpen, name_map: NameMap):
        l = event.loan
        user_link = self.link_to_address(l.owner, name_map)
        asset = ' ' + Asset(l.collateral_asset).pretty_str
        target_asset = Asset(l.target_asset).pretty_str

        return (
            f'🏦→ Loan open {user_link}\n'
            f'Collateral deposited: {pretty_money(l.collateral_float, postfix=asset)}'
            f' ({pretty_dollar(event.collateral_usd)})\n'
            f'CR: x{pretty_money(l.collateralization_ratio)}\n'
            f'Debt: {pretty_dollar(l.debt_usd)}\n'
            f'Target asset: {target_asset}\n'
            f'{self.LENDING_DASHBOARD_URL}'
        )

    def notification_text_loan_repayment(self, event: AlertLoanRepayment, name_map: NameMap):
        loan = event.loan
        user_link = self.link_to_address(loan.owner, name_map)
        asset = ' ' + Asset(loan.collateral_asset).pretty_str

        return (
            f'🏦← Loan repayment {user_link}\n'
            f'Collateral withdrawn: {pretty_money(loan.collateral_float, postfix=asset)}'
            f' ({pretty_dollar(event.collateral_usd)})\n'
            f'Debt repaid: {pretty_dollar(loan.debt_repaid_usd)}\n'
            f'{self.LENDING_DASHBOARD_URL}'
        )

    def notification_lending_stats(self, event: AlertLendingStats):
        (borrower_count_delta, curr, lending_tx_count_delta, rune_burned_rune_delta, total_borrowed_amount_delta,
         total_collateral_value_delta, cr) = self._lending_stats_delta(event)

        paused_str = '🛑 Paused!\n' if event.current.is_paused else ''

        return (
            f'Lending stats\n\n'
            f'{paused_str}'
            f'🙋‍️ Borrower count: {pretty_money(curr.borrower_count)} {borrower_count_delta}\n'
            f'📝 Tx count: {pretty_money(curr.lending_tx_count)} {lending_tx_count_delta}\n'
            f'💰 Total collateral: {short_dollar(curr.total_collateral_value_usd)} {total_collateral_value_delta}\n'
            f'💸 Total borrowed: {short_dollar(curr.total_borrowed_amount_usd)} {total_borrowed_amount_delta}\n'
            f'{self._lend_pool_desc(event)}'
            f"Collateral Ratio: {pretty_money(cr)}\n"
            f'❤️‍🔥 Rune burned: {short_rune(curr.rune_burned_rune)} {rune_burned_rune_delta}\n\n'
            f'{self.LENDING_LINK}'
        )

    def notification_lending_open_back_up(self, event: AlertLendingOpenUpdate):
        available_collateral = short_money(event.pool_state.collateral_available)
        pool_name = self.LEND_DICT.get(event.asset, event.asset)
        return (
            f'🟢 A lending opportunity is now available in the {self.pretty_asset(event.asset)} pool.\n'
            f'{available_collateral} {pool_name} can be deposited as collateral.\n'
            f'Current fill level: {format_percent(event.pool_state.fill, total=1.0)}.\n'
        )

    # ------ TRADE ACCOUNT ------

    def notification_text_trade_account_move(self, event: AlertTradeAccountAction, name_map: NameMap):
        action_str = 'deposit' if event.is_deposit else 'withdrawal'
        from_link, to_link, amt_str = self._trade_acc_from_to_links(event, name_map, formatting=False)
        return (
            f"🏦 Trade account {action_str}\n"
            f"👤 From {from_link}"
            f" to {to_link}\n"
            f"Total: {amt_str}\n"
            f"{self.link_to_tx(event.tx_hash)}"
        )

    def notification_text_trade_account_summary(self, e: AlertTradeAccountStats):
        top_vaults_str = self._top_trade_vaults(e, 4, formatting=False)

        delta_holders = bracketify(
            up_down_arrow(e.prev.vaults.total_traders, e.curr.vaults.total_traders, int_delta=True)) if e.prev else ''

        delta_balance = bracketify(
            up_down_arrow(e.prev.vaults.total_usd, e.curr.vaults.total_usd, percent_delta=True)) if e.prev else ''

        tr_swap_volume_curr, tr_swap_volume_prev = e.curr_and_prev_trade_volume_usd
        delta_volume = bracketify(
            up_down_arrow(tr_swap_volume_prev, tr_swap_volume_curr, percent_delta=True)) if e.prev else ''

        parts = [
            (
                f"⚖️ Trade assets summary 24H\n\n"
                f"Total holders: {pretty_money(e.curr.vaults.total_traders)}"
                f" {delta_holders}\n"
                f"Total trade assets: {short_money(e.curr.vaults.total_usd)}"
                f" {delta_balance}\n"
                f"Deposits: {short_money(e.curr.trade_deposit_count, integer=True)}"
                f" {bracketify(short_dollar(e.curr.trade_deposit_vol_usd))}\n"
                f"Withdrawals: {short_money(e.curr.trade_withdrawal_count, integer=True)}"
                f" {bracketify(short_dollar(e.curr.trade_withdrawal_vol_usd))}\n"
                f"Trade volume: {short_dollar(tr_swap_volume_curr)} {delta_volume}\n"
                f"Swaps of trade assets: {short_money(e.curr.trade_swap_count, integer=True)}"
                f" {bracketify(up_down_arrow(e.prev.trade_swap_count, e.curr.trade_swap_count, int_delta=True))}\n"
            ),
            (
                f"Highest used:\n"
                f"{top_vaults_str}"
            )
        ]

        return self.smart_split(parts)

    # ------- RUNEPOOL --------

    def notification_runepool_action(self, event: AlertRunePoolAction, name_map: NameMap):
        action_str = 'deposit' if event.is_deposit else 'withdrawal'
        from_link = self.link_to_address(event.actor, name_map)
        to_link = self.link_to_address(event.destination_address, name_map)
        amt_str = f"{pretty_rune(event.amount)}"

        if event.is_deposit:
            route = f"👤{from_link} ➡️ RUNEPool"
        else:
            route = f"RUNEPool ➡️ 👤{to_link}"

        if event.affiliate:
            aff_collector = self.name_service.get_affiliate_name(event.affiliate)
            aff_collector = f'{aff_collector} ' if aff_collector else ''

            aff_text = f'{aff_collector}Aff. fee: {format_percent(event.affiliate_rate, 1)}\n'
        else:
            aff_text = ''

        return (
            f"🏦 RUNEPool {action_str}\n"
            f"{route}\n"
            f"Total: {amt_str} ({pretty_dollar(event.usd_amount)})\n"
            f"{aff_text}"
            f"{self.link_to_tx(event.tx_hash)}"
        )

    def notification_runepool_stats(self, event: AlertRunepoolStats):
        n_providers_delta, pnl_delta, rune_delta, share_delta = self._runepool_deltas(event)

        return (
            f'🏦 RUNEPool stats\n'
            f'Total value: {pretty_rune(event.current.rune_value)} {rune_delta}\n'
            f'Share of providers: {pretty_percent(event.current.providers_share, signed=False)} {share_delta}\n'
            f'PnL: {pretty_rune(event.current.pnl)} {pnl_delta}\n'
            f'Providers: {short_money(event.current.n_providers, integer=True)} {n_providers_delta}\n'
            f'Avg. value per provider: {pretty_rune(event.current.avg_deposit)}\n'
        )

    # ------ Network indentifiers ------

    @staticmethod
    def notification_text_chain_id_changed(event: AlertChainIdChange):
        return (
            f'🆔 Network identifier has changed\n\n'
            f'Old: "{event.prev_chain_id}"\n'
            f'New: "{event.curr_chain_id}"'
        )

    # ------- Rune burn -------

    @staticmethod
    def notification_rune_burn(e: EventRuneBurn):
        return f'{short_rune(e.last_24h_burned_rune)} $RUNE was burned today ({short_dollar(e.last_24h_burned_usd)})'

        # trend = 'Deflation' if e.deflation_percent > 0 else 'Inflation'
        # return (
        #     f'🔥 Rune burned\n\n'
        #     f'Last {int(e.tally_days)} days burned: {pretty_rune(e.delta_rune)} '
        #     f'({pretty_dollar(e.delta_usd)})\n'
        #     f'Total burned: {pretty_rune(e.total_burned_rune)} '
        #     f'({pretty_dollar(e.total_burned_usd)})\n'
        #     f"Burning {pretty_percent(e.system_income_burn_percent, signed=False)} of the system's income, "
        #     f"approximately {pretty_rune(e.yearly_burn_prediction)} Runes will be burned in a year.\n"
        #     f"{trend} is {pretty_percent(e.deflation_percent, signed=False)}."
        # )
