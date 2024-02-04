import logging
from abc import ABC
from datetime import datetime
from typing import List, Optional

from math import ceil
from semver import VersionInfo

from aionode.types import ThorChainInfo, ThorBalances, ThorSwapperClout
from localization.achievements.ach_eng import AchievementsEnglishLocalization
from proto.types import ThorName
from services.jobs.fetch.circulating import ThorRealms
from services.jobs.fetch.runeyield.borrower import LoanReportCard
from services.lib.config import Config
from services.lib.constants import thor_to_float, THOR_BLOCK_TIME, DEFAULT_CEX_NAME, \
    DEFAULT_CEX_BASE_ASSET, bp_to_percent, LOAN_MARKER
from services.lib.date_utils import format_time_ago, now_ts, seconds_human, MINUTE, DAY
from services.lib.explorers import get_explorer_url_to_address, Chains, get_explorer_url_to_tx, \
    get_explorer_url_for_node, get_pool_url, get_thoryield_address, get_ip_info_link
from services.lib.midgard.name_service import NameService, add_thor_suffix, NameMap
from services.lib.money import format_percent, pretty_money, short_address, short_money, \
    calc_percent_change, adaptive_round_to_str, pretty_dollar, emoji_for_percent_change, Asset, short_dollar, \
    RAIDO_GLYPH, short_rune, pretty_percent, chart_emoji, pretty_rune
from services.lib.texts import progressbar, link, pre, code, bold, x_ses, ital, link_with_domain_text, \
    up_down_arrow, bracketify, plural, join_as_numbered_list, regroup_joining, shorten_text, cut_long_text
from services.lib.utils import grouper, run_once
from services.lib.w3.dex_analytics import DexReport, DexReportEntry
from services.lib.w3.token_record import AmountToken
from services.models.cap_info import ThorCapInfo
from services.models.flipside import AlertKeyStats
from services.models.last_block import BlockProduceState, EventBlockSpeed
from services.models.loans import AlertLoanOpen, AlertLoanRepayment, AlertLendingStats
from services.models.lp_info import LiquidityPoolReport
from services.models.mimir import MimirChange, MimirHolder, MimirEntry, MimirVoting, MimirVoteOption
from services.models.mimir_naming import MimirUnits, NEXT_CHAIN_VOTING_MAP
from services.models.net_stats import NetworkStats
from services.models.node_info import NodeSetChanges, NodeInfo, NodeVersionConsensus, NodeEventType, NodeEvent, \
    EventBlockHeight, EventDataSlash, calculate_security_cap_rune, EventProviderBondChange, \
    EventProviderStatus
from services.models.pol import AlertPOL
from services.models.pool_info import PoolInfo, PoolChanges, PoolMapPair
from services.models.price import AlertPrice, RuneMarketInfo
from services.models.queue import QueueInfo
from services.models.s_swap import AlertSwapStart
from services.models.savers import how_much_savings_you_can_add, AlertSaverStats
from services.models.transfer import RuneTransfer, RuneCEXFlow
from services.models.tx import ThorTx, ThorSubTx, EventLargeTransaction
from services.models.tx_type import TxType
from services.notify.channel import Messengers

CREATOR_TG = '@account1242'

URL_THOR_SWAP = 'https://app.thorswap.finance/'

URL_LEADERBOARD_MCCN = 'https://leaderboard.thornode.org/'


class BaseLocalization(ABC):  # == English
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.name_service: Optional[NameService] = None
        self.name = self.__class__.__name__
        self.ach = AchievementsEnglishLocalization()

    # ----- WELCOME ------

    TEXT_DECORATION_ENABLED = True

    LOADING = '⌛ <i>Loading...</i>'
    LONG_DASH = '–'
    SUCCESS = '✅ Success!'
    ERROR = '❌ Error!'
    NOT_READY = 'Sorry but the data is not ready yet.'
    ND = 'N/D'
    NA = 'N/A'

    LIST_NEXT_PAGE = 'Next page »'
    LIST_PREV_PAGE = '« Prev. page'

    THORCHAIN_LINK = 'https://thorchain.org/'
    R = 'Rune'

    BOT_LOADING = '⌛ Bot has been recently restarted and is still loading. Please try again after 1-2 minutes.'

    RATE_LIMIT_WARNING = '🔥 <b>Attention!</b>\n' \
                         'You are apparently receiving too many personal notifications. ' \
                         'You will be restricted in receiving them for some time. ' \
                         'Check your /settings to adjust the frequency of notifications.'

    SHORT_MONEY_LOC = None  # default is Eng

    @property
    def this_bot_name(self):
        return self.cfg.telegram.bot.username

    @property
    def url_start_me(self):
        return f'https://telegram.me/{self.this_bot_name}?start=1'

    @property
    def alert_channel_name(self):
        channels = self.cfg.broadcasting.channels
        for c in channels:
            if c['type'] == Messengers.TELEGRAM:
                return c['name']
        return ''

    @staticmethod
    def _cap_progress_bar(info: ThorCapInfo):
        return (f'{progressbar(info.pooled_rune, info.cap, 10)} '
                f'({format_percent(info.pooled_rune, info.cap)})')

    # ---- WELCOME ----
    def help_message(self):
        return (
            f"This bot is for {link(self.THORCHAIN_LINK, 'THORChain')} monitoring.\n"
            f"Command list:\n"
            f"/help – this help page\n"
            f"/start – start/restart the bot\n"
            f"/lang – set the language\n"
            f"/cap – the current liquidity cap\n"
            f"/price – the current Rune price.\n"
            f"/queue – TX queue info\n"
            f"/nodes – list of THOR Nodes\n"
            f"/stats – THORChain stats\n"
            f"/chains – Connected chains\n"
            f"/lp – check your LP yield\n"
            f"<b>⚠️ All notifications are forwarded to {self.alert_channel_name} channel!</b>\n"
            f"🤗 Support and feedback: {CREATOR_TG}."
        )

    def welcome_message(self, info: ThorCapInfo):
        return (
            f"Hello! Here you can find THORChain metrics and review your liquidity results.\n"
            f"The {self.R} price is <code>${info.price:.3f}</code> now.\n"
            f"<b>⚠️ All notifications are forwarded to {self.alert_channel_name} channel!</b>\n"
            f"🤗 Support and feedback: {CREATOR_TG}."
        )

    def unknown_command(self):
        return (
            "🙄 Sorry, I didn't understand that command.\n"
            "Use /help to see available commands."
        )

    # ----- MAIN MENU ------

    BUTTON_MM_MY_ADDRESS = '🏦 My wallets'
    BUTTON_MM_METRICS = '📐 Metrics'
    BUTTON_MM_SETTINGS = f'⚙️ Settings'
    BUTTON_MM_MAKE_AVATAR = f'🦹‍️️ THOR avatar'
    BUTTON_MM_NODE_OP = '🤖 NodeOp tools'

    # ------- MY WALLETS MENU -------

    BUTTON_SM_ADD_ADDRESS = '➕ Add an address'
    BUTTON_BACK = '🔙 Back'
    BUTTON_SM_BACK_TO_LIST = '🔙 Back to the list'
    BUTTON_SM_BACK_MM = '🔙 Main menu'

    BUTTON_SM_SUMMARY = '💲 Summary'

    BUTTON_VIEW_RUNE_DOT_YIELD = '🌎 View it on THORYield'
    BUTTON_VIEW_VALUE_ON = 'Show value: ON'
    BUTTON_VIEW_VALUE_OFF = 'Show value: OFF'

    BUTTON_LP_PROT_ON = 'IL prot.: ON'
    BUTTON_LP_PROT_OFF = 'IL prot.: OFF'

    BUTTON_TRACK_BALANCE_ON = 'Track balance: ON'
    BUTTON_TRACK_BALANCE_OFF = 'Track balance: OFF'

    BUTTON_TRACK_BOND_ON = 'Track bond: ON'
    BUTTON_TRACK_BOND_OFF = 'Track bond: OFF'

    BUTTON_SET_RUNE_ALERT_LIMIT = 'Set min limit'

    BUTTON_REMOVE_THIS_ADDRESS = '❌ Remove this address'

    BUTTON_LP_SUBSCRIBE = '🔔 Subscribe'
    BUTTON_LP_UNSUBSCRIBE = '🔕 Unsubscribe'
    TEXT_SUBSCRIBE_TO_LP = '🔔 Would you like to sign up for automatic notifications for this position? ' \
                           'You\'ll be receiving LP/Savers yield report at the same time ' \
                           'every other day, week, or month.'
    BUTTON_LP_UNSUBSCRIBE_ALL = '🔕 Unsubscribe from all'
    BUTTON_LP_PERIOD_1D = 'Every day'
    BUTTON_LP_PERIOD_1W = 'Every week'
    BUTTON_LP_PERIOD_1M = 'Every month'
    ALERT_SUBSCRIBED_TO_LP = '🔔 You have subscribed!'
    ALERT_UNSUBSCRIBED_FROM_LP = '🔕 You have unsubscribed!'
    ALERT_UNSUBSCRIBE_FAILED = 'Failed to unsubscribe. Please try again later.'

    @staticmethod
    def text_error_delivering_report(self, e, address, pool):
        return (
            f'🔥 Error delivering report: {e}. '
            f'You are unsubscribed from the notification. '
            f'Try to subscribe later or contact the developer {CREATOR_TG}.\n\n'
            f'Address {ital(address)}, pool {ital(pool)}'
        )

    @staticmethod
    def text_subscribed_to_lp(period):
        next_ts = now_ts() + period
        next_date = datetime.utcfromtimestamp(next_ts).strftime('%Y-%m-%d %H:%M:%S')
        next_date += ' UTC'
        return f'🔔 <b>Congratulations!</b> You have successfully subscribed.\n' \
               f'The next update will come to you on {ital(next_date)}.'

    TEXT_WALLETS_INTRO = (
        'Here you can add the addresses of the wallets you want to follow. The following features are available:\n'
        '👉 Liquidity Provisioning\n'
        '👉 Savings vaults\n'
        '👉 Track balances and actions\n'
        '👉 Provision of Bond to nodes 🆕\n'
        '👉 Loans 🆕\n'
    )
    TEXT_NO_ADDRESSES = "🔆 You have not added any addresses yet. Send me one."
    TEXT_YOUR_ADDRESSES = '🔆 You added addresses:'
    TEXT_INVALID_ADDRESS = code('⛔️ Invalid address!')
    TEXT_SELECT_ADDRESS_ABOVE = 'Please select one from above. ☝️ '
    TEXT_SELECT_ADDRESS_SEND_ME = 'If you want to add one more, please send me it. 👇'
    TEXT_LP_NO_POOLS_FOR_THIS_ADDRESS = "📪 <i>This address doesn't participate in any liquidity pools.</i>"
    TEXT_CANNOT_ADD = '😐 Sorry, but you cannot add this address.'

    TEXT_INVALID_LIMIT = '⛔ <b>Invalid number!</b> Please enter a positive number.'
    TEXT_ANY = 'Any amount'

    BUTTON_WALLET_SETTINGS = '⚙️ Wallet settings'
    BUTTON_WALLET_NAME = 'Set name'

    BUTTON_CLEAR_NAME = 'None (use the address)'

    BUTTON_CANCEL = 'Cancel'

    TEXT_NAME_UNSET = 'The name has been unlinked.'

    def text_set_rune_limit_threshold(self, address, curr_limit):
        return (
            f'🎚 Enter the minimum amount of Rune as the threshold '
            f'for triggering transfer alerts at this address ({address}).\n'
            f'It is now equal to {ital(short_rune(curr_limit))}.\n\n'
            f'You can send me the number with a text message or choose one of the options on the buttons.'
        )

    @staticmethod
    def text_my_wallet_settings(address, name='', min_limit=None):
        name_str = ''
        if name:
            name_str = f' ({ital(name)})'

        if min_limit is not None:
            limit_str = f'\n\n📨 Transactions ≥ {short_rune(min_limit)} are tracked.'
        else:
            limit_str = ''

        return (f'🎚 Wallet "{code(address)}"{name_str} settings.'
                f'{limit_str}')

    @staticmethod
    def text_my_wallet_name_changed(address, name):
        return f'🎉 The new name is set to "{code(name)}" for wallet with address "{code(address)}".'

    @staticmethod
    def text_wallet_name_dialog(address, name):
        message = (
            f'This name will appear in the wallet list instead of the address ({pre(address)}) for your convenience.\n'
        )
        if name:
            message += f'The current name is "{code(name)}".\n'
        message += '<b>Please, send me a name by message.</b> 👇'
        return message

    def text_lp_img_caption(self):
        bot_link = "@" + self.this_bot_name
        start_me = self.url_start_me
        return f'Generated by {link(start_me, bot_link)}'

    LP_PIC_TITLE = 'liquidity'
    LP_PIC_POOL = 'POOL'
    LP_PIC_RUNE = 'RUNE'
    LP_PIC_ADDED = 'Added'
    LP_PIC_WITHDRAWN = 'Withdrawn'
    LP_PIC_REDEEM = 'Redeemable'
    LP_PIC_GAIN_LOSS = 'Gain / Loss'
    LP_PIC_IN_USD = 'in USD'
    LP_PIC_IN_USD_CAP = 'or in USD'
    LP_PIC_R_RUNE = f'In {RAIDO_GLYPH}une'
    LP_PIC_IN_ASSET = 'or in {0}'
    LP_PIC_ADDED_VALUE = 'Added value'
    LP_PIC_WITHDRAWN_VALUE = 'Withdrawn value'
    LP_PIC_CURRENT_VALUE = 'Current value +fee'
    LP_PIC_PRICE_CHANGE = 'Price change'
    LP_PIC_PRICE_CHANGE_2 = 'since the first addition'
    LP_PIC_LP_VS_HOLD = 'LP vs HOLD'
    LP_PIC_LP_APY = 'LP APY'
    LP_PIC_LP_APY_OVER_LIMIT = 'Too much %'
    LP_PIC_EARLY = 'Early...'
    LP_PIC_FOOTER = ""
    LP_PIC_FEES = 'Fees earned'
    LP_PIC_IL_PROTECTION = 'IL protection'
    LP_PIC_NO_NEED_PROTECTION = 'Not needed'
    LP_PIC_EARLY_TO_PROTECT = 'Too early...'
    LP_PIC_PROTECTION_DISABLED = 'Disabled'

    LP_PIC_SUMMARY_HEADER = 'Liquidity pools summary'
    LP_PIC_SUMMARY_ADDED_VALUE = 'Added value'
    LP_PIC_SUMMARY_WITHDRAWN_VALUE = 'Withdrawn'
    LP_PIC_SUMMARY_CURRENT_VALUE = 'Current value'
    LP_PIC_SUMMARY_TOTAL_GAIN_LOSS = 'Total gain/loss'
    LP_PIC_SUMMARY_TOTAL_GAIN_LOSS_PERCENT = 'Total gain/loss %'
    LP_PIC_SUMMARY_AS_IF_IN_RUNE = f'Total as {RAIDO_GLYPH}'
    LP_PIC_SUMMARY_AS_IF_IN_USD = 'Total as $'
    LP_PIC_SUMMARY_TOTAL_LP_VS_HOLD = 'Total LP vs Hold $'
    LP_PIC_SUMMARY_NO_WEEKLY_CHART = "No weekly chart, sorry"

    def label_for_pool_button(self, pool_name):
        short_name = cut_long_text(pool_name)
        if LOAN_MARKER in pool_name:
            # strip LOAN_MARKER
            return f'Loan: {short_name[len(LOAN_MARKER):]}'

        if Asset(pool_name).is_synth:
            return 'Sv:' + short_name
        else:
            return 'LP:' + short_name

    def pic_lping_days(self, total_days, first_add_ts, extra=''):
        start_date = datetime.fromtimestamp(first_add_ts).strftime('%d.%m.%Y')
        day_count_str = plural(total_days, 'day', 'days')
        extra = ' ' + extra if extra else ''
        return f'{ceil(total_days)} {day_count_str}{extra} ({start_date})'

    TEXT_PLEASE_WAIT = '⏳ <b>Please wait...</b>'

    def text_lp_loading_pools(self, address):
        return f'{self.TEXT_PLEASE_WAIT}\n' \
               f'Loading pools information for {pre(address)}...'

    def explorer_link_to_address_with_domain(self, address, chain=Chains.THOR):
        net = self.cfg.network_id
        return link_with_domain_text(get_explorer_url_to_address(net, chain, address))

    @staticmethod
    def text_balances(balances: ThorBalances, title='Account balance:'):
        if not balances or not len(balances.assets):
            return ''
        items = []
        for coin in balances.assets:
            postfix = ' ' + Asset(coin.asset).pretty_str
            items.append(pre(short_money(coin.amount_float) + postfix))

        if len(items) == 1:
            result = f'{title} {items[0]}'
        else:
            result = '\n'.join([title] + items)
        return result + '\n\n'

    def text_inside_my_wallet_title(self, address, pools, balances: ThorBalances, min_limit: float, chain,
                                    thor_name: Optional[ThorName], local_name, clout: Optional[ThorSwapperClout]):
        if pools:
            title = '\n'
            footer = "\n\n👇 Click on the button to get a detailed card."
        else:
            title = self.TEXT_LP_NO_POOLS_FOR_THIS_ADDRESS + '\n\n'
            footer = ''

        explorer_links = self.explorer_link_to_address_with_domain(address)

        balance_str = self.text_balances(balances)

        if clout:
            score_text = pretty_rune(thor_to_float(clout.score))
            reclaimed_text = pretty_rune(thor_to_float(clout.reclaimed))
            spent_text = pretty_rune(thor_to_float(clout.spent))
            clout_text = f'{bold(score_text)} score | {bold(reclaimed_text)} reclaimed | {bold(spent_text)} spent'
            balance_str += f'Swapper clout: {clout_text}\n\n'

        acc_caption = ''
        if thor_name:
            acc_caption += f' | THORName: {pre(add_thor_suffix(thor_name))}'
        if local_name:
            acc_caption += f' | Local name: {pre(local_name)}'

        thor_yield_url = get_thoryield_address(self.cfg.network_id, address, chain)
        thor_yield_link = link(thor_yield_url, 'THORYield')

        if min_limit is not None:
            limit_str = f'📨 Transactions ≥ {short_rune(min_limit)} are tracked.\n'
        else:
            limit_str = ''

        return (
            f'🛳️ Account "{code(address)}"{acc_caption}\n'
            f'{title}'
            f'{balance_str}'
            f'{limit_str}'
            f"🔍 Explorer: {explorer_links}\n"
            f"🌎 View it on {thor_yield_link}"
            f'{footer}'
        )

    def text_lp_today(self):
        today = datetime.now().strftime('%d.%m.%Y')
        return f'Today is {today}'

    TEXT_LP_NO_LOAN_FOR_THIS_ADDRESS = "📪 <i>There are no loans for this address in the pool {pool}</i>"

    def notification_text_loan_card(self, card: LoanReportCard, local_name='', unsub_id=''):
        # todo
        return (
            f'🏦 <b>Loan</b> | {card.pool} | {card.address}\n'
        )

    # ------- CAP -------

    @staticmethod
    def thor_site():
        return URL_THOR_SWAP

    @property
    def show_add_more(self):
        return self.cfg.get('tx.show_add_more', True)

    def can_add_more_lp_text(self, cap: ThorCapInfo):
        if cap.can_add_liquidity:
            return (
                f'🤲🏻 You can add {bold(short_rune(cap.how_much_rune_you_can_lp))} {self.R} '
                f'or {bold(short_dollar(cap.how_much_usd_you_can_lp))} more liquidity.'
            )
        else:
            return f"🚫 You can't add more liquidity. The cap is reached."

    def notification_text_cap_change(self, old: ThorCapInfo, new: ThorCapInfo):
        up = old.cap < new.cap
        verb = "has been increased" if up else "has been decreased"
        arrow = '⬆️' if up else '⚠️ ⬇️'
        message = (
            f'{arrow} <b>Pool cap {verb} from {short_money(old.cap)} to {short_money(new.cap)}!</b>\n'
            f'Currently <b>{short_money(new.pooled_rune)}</b> {self.R} are in the liquidity pools.\n'
            f'{self._cap_progress_bar(new)}\n'
            f'{self.can_add_more_lp_text(new)}\n'
            f'The price of {self.R} in the pools is {code(pretty_dollar(new.price))}.\n'
            f'{self.thor_site()}'
        )
        return message

    def notification_text_cap_full(self, cap: ThorCapInfo):
        return (
            '🙆‍♀️ <b>Liquidity has reached the capacity limit!</b>\n'
            'Please stop adding liquidity. '
            'You will get refunded if you provide liquidity from now on!\n'
            f'Now <i>{short_money(cap.pooled_rune)} {self.R}</i> of '
            f"<i>{short_money(cap.cap)} {self.R}</i> max pooled.\n"
            f"{self._cap_progress_bar(cap)}"
        )

    def notification_text_cap_opened_up(self, cap: ThorCapInfo):
        return (
            '💡 <b>There is free space in liquidity pools!</b>\n'
            f'<i>{short_money(cap.pooled_rune)} {self.R}</i> of '
            f"<i>{short_money(cap.cap)} {self.R}</i> max pooled.\n"
            f"{self._cap_progress_bar(cap)}\n"
            f'🤲🏻 You can add {bold(short_money(cap.how_much_rune_you_can_lp))} {self.R} '
            f'or {bold(short_dollar(cap.how_much_usd_you_can_lp))}.\n👉🏻 {self.thor_site()}'
        )

    # ------ PRICE -------

    PRICE_GRAPH_TITLE = f'THORChain Rune price, USD'
    PRICE_GRAPH_LEGEND_DET_PRICE = f'Deterministic {RAIDO_GLYPH} price'
    PRICE_GRAPH_LEGEND_ACTUAL_PRICE = f'Pool {RAIDO_GLYPH} price'
    PRICE_GRAPH_LEGEND_CEX_PRICE = f'CEX {RAIDO_GLYPH} price'
    PRICE_GRAPH_VOLUME_SWAP_NORMAL = 'Swap volume'
    PRICE_GRAPH_VOLUME_SWAP_SYNTH = 'Synth volume'
    PRICE_GRAPH_VOLUME_SWAP_ADD = 'Add volume'
    PRICE_GRAPH_VOLUME_SWAP_WITHDRAW = 'Withdraw volume'

    # ------- NOTIFY TXS -------

    TEXT_MORE_TXS = ' and {n} more'

    def links_to_txs(self, txs: List[ThorSubTx], main_run_txid='', max_n=2):
        net = self.cfg.network_id
        items = []
        for tx in txs[:max_n]:
            tx_id = tx.tx_id or main_run_txid
            if tx_id:
                # todo use self.pretty_asset
                a = Asset(tx.first_asset)
                chain = a.chain if a.chain else Chains.THOR
                if a.is_synth:
                    chain = Chains.THOR
                url = get_explorer_url_to_tx(net, chain, tx_id)
                items.append(link(url, text=a.pretty_str_no_emoji))

        result = ', '.join(items)

        extra_n = len(txs) - max_n
        if extra_n > 0:
            result += self.TEXT_MORE_TXS.format(n=extra_n)
        return result

    def link_to_explorer_user_address_for_tx(self, tx: ThorTx, name_map):
        address, _ = tx.sender_address_and_chain
        return self.link_to_address(tx.sender_address, name_map)  # Chains.THOR is always here, that is deliberate!

    @staticmethod
    def lp_tx_calculations(usd_per_rune, pool_info: PoolInfo, tx: ThorTx):
        total_usd_volume = tx.full_rune * usd_per_rune
        pool_depth_usd = pool_info.usd_depth(usd_per_rune) if pool_info else 0.0

        percent_of_pool = tx.what_percent_of_pool(pool_info)
        rp, ap = tx.symmetry_rune_vs_asset()
        rune_side_usd = tx.rune_amount * usd_per_rune

        rune_side_usd_short = short_dollar(rune_side_usd)
        asset_side_usd_short = short_dollar(total_usd_volume - rune_side_usd)

        chain = Asset(tx.first_pool).chain

        return (
            ap, asset_side_usd_short, chain, percent_of_pool, pool_depth_usd,
            rp, rune_side_usd_short,
            total_usd_volume
        )

    @staticmethod
    def format_op_amount(amt):
        return bold(short_money(amt))

    def format_aggregator(self, a: AmountToken):
        chain = ''
        if a.token.chain_id == Chains.web3_chain_id(Chains.ETH):
            chain = Chains.ETH
        elif a.token.chain_id == Chains.web3_chain_id(Chains.AVAX):
            chain = Chains.AVAX
        elif a.token.chain_id == Chains.web3_chain_id(Chains.BSC):
            chain = Chains.BSC
        if a.amount > 0:
            return f'{self.format_op_amount(a.amount)} {chain}.{a.token.symbol}'
        else:
            return f'{chain}.{a.token.symbol}'

    def _get_asset_summary_string(self, tx, in_only=False, out_only=False):
        ends = tx.get_asset_summary(in_only=in_only, out_only=out_only)
        ends = {self.pretty_asset(a): v for a, v in ends.items()}
        return ', '.join(f"{self.format_op_amount(amount)} {asset}" for asset, amount in ends.items())

    def format_swap_route(self, tx: ThorTx, usd_per_rune):
        input_str = self._get_asset_summary_string(tx, in_only=True)
        output_str = self._get_asset_summary_string(tx, out_only=True)

        route_components = []
        dex = tx.dex_info

        if dex.swap_in:
            route_components.append(self.format_aggregator(dex.swap_in))
            if dex.swap_in.aggr_name:
                route_components.append(dex.swap_in.aggr_name)

        route_components.extend((input_str, '⚡', output_str))

        if dex.swap_out:
            if dex.swap_out.aggr_name:
                route_components.append(dex.swap_out.aggr_name)
            route_components.append(self.format_aggregator(dex.swap_out))

        route_str = ' → '.join(route_components)

        return f"{route_str} ({short_dollar(tx.get_usd_volume(usd_per_rune))})"

    def _exclamation_sign(self, value, cfg_key='', ref=100):
        exclamation_limit = self.cfg.as_float(f'tx.exclamation.{cfg_key}', 10000) if cfg_key else ref
        if value >= exclamation_limit * 2:
            return '‼️'
        elif value > exclamation_limit:
            return '❗'
        else:
            return ''

    @run_once
    def tx_add_date_if_older_than(self):
        return self.cfg.as_interval('tx.add_date_if_older_than', '3h')

    def tx_date(self, tx: ThorTx):
        now = now_ts()
        if tx.date_timestamp < now - self.tx_add_date_if_older_than():
            return self.format_time_ago(now - tx.date_timestamp)

    MIN_PERCENT_TO_SHOW = 1.0

    def notification_text_large_single_tx(self, e: EventLargeTransaction, name_map: NameMap):
        usd_per_rune, pool_info, tx = e.usd_per_rune, e.pool_info, e.transaction

        (ap, asset_side_usd_short, chain, percent_of_pool, pool_depth_usd, rp, rune_side_usd_short,
         total_usd_volume) = self.lp_tx_calculations(usd_per_rune, pool_info, tx)

        heading = ''
        if tx.type == TxType.ADD_LIQUIDITY:
            if tx.is_savings:
                heading = f'🐳→💰 <b>Add to savings vault</b>'
            else:
                heading = f'🐳→⚡ <b>Add liquidity</b>'
        elif tx.type == TxType.WITHDRAW:
            if tx.is_savings:
                heading = f'🐳←💰 <b>Withdraw from savings vault</b>'
            else:
                heading = f'🐳←⚡ <b>Withdraw liquidity</b>'
        elif tx.type == TxType.DONATE:
            heading = f'🙌 <b>Donation to the pool</b>'
        elif tx.type == TxType.SWAP:
            if tx.is_streaming:
                heading = f'🌊 <b>Streaming swap finished</b> 🔁'
            else:
                heading = f'🐳 <b>Swap</b> 🔁'
        elif tx.type == TxType.REFUND:
            heading = f'🐳 <b>Refund</b> ↩️❗'

        if tx.is_pending:
            heading += ital(' [Pending]')

        # it is old
        if date_text := self.tx_date(tx):
            heading += ital(f' {date_text}')

        asset = Asset(tx.first_pool).name

        content = f''

        if tx.type in (TxType.ADD_LIQUIDITY, TxType.WITHDRAW, TxType.DONATE):
            if tx.affiliate_fee > 0:
                aff_fee_usd = tx.get_affiliate_fee_usd(usd_per_rune)
                mark = self._exclamation_sign(aff_fee_usd, 'fee_usd_limit')
                aff_text = f'Affiliate fee: {bold(short_dollar(aff_fee_usd))}{mark} ' \
                           f'({format_percent(tx.affiliate_fee, 1)})\n'
            else:
                aff_text = ''

            ilp_rune = tx.meta_withdraw.ilp_rune if tx.meta_withdraw else 0
            if ilp_rune > 0:
                ilp_usd = ilp_rune * usd_per_rune
                mark = self._exclamation_sign(ilp_usd, 'ilp_usd_limit')
                ilp_text = f'🛡️ Impermanent loss protection paid: {code(short_rune(ilp_rune))}{mark} ' \
                           f'({short_dollar(ilp_usd)})\n'
            else:
                ilp_text = ''

            if tx.is_savings:
                cap = None  # it will stop standard LP cap from being shown

                amount_more, asset_more, saver_pb, saver_cap, saver_percent = \
                    self.get_savers_limits(pool_info, usd_per_rune, e.mimir, tx.asset_amount)
                saver_cap_part = f'Savers cap is {saver_pb} full. '

                # todo
                if self.show_add_more and amount_more > 0:
                    saver_cap_part += f'You can add {pre(short_money(amount_more))} {pre(asset_more)} more.'

                vault_percent_part = f", {saver_percent:.2f}% of vault" if saver_percent >= self.MIN_PERCENT_TO_SHOW \
                    else ''
                asset_part = f"{bold(short_money(tx.asset_amount))} {asset}"

                content = (
                    f"{asset_part} ({code(short_dollar(total_usd_volume))}{vault_percent_part})\n"
                    f"{aff_text}"
                    f"{ilp_text}"
                    f"{saver_cap_part}"
                )

            else:
                rune_part = f"{bold(short_money(tx.rune_amount))} {self.R} ({rune_side_usd_short}) ↔️ "
                asset_part = f"{bold(short_money(tx.asset_amount))} {asset} ({asset_side_usd_short})"
                pool_depth_part = f'Pool depth is {bold(short_dollar(pool_depth_usd))} now.'
                pool_percent_part = f" ({percent_of_pool:.2f}% of pool)" if percent_of_pool >= self.MIN_PERCENT_TO_SHOW \
                    else ''

                content = (
                    f"{rune_part}{asset_part}\n"
                    f"Total: {code(short_dollar(total_usd_volume))}{pool_percent_part}\n"
                    f"{aff_text}"
                    f"{ilp_text}"
                    f"{pool_depth_part}"
                )

        elif tx.type == TxType.REFUND:
            reason = shorten_text(tx.meta_refund.reason, 180)
            content = (
                    self.format_swap_route(tx, usd_per_rune) +
                    f"\nReason: {pre(reason)}"
            )
        elif tx.type == TxType.SWAP:
            content = self.format_swap_route(tx, usd_per_rune)
            slip_str = f'{tx.meta_swap.trade_slip_percent:.3f} %'
            l_fee_usd = tx.meta_swap.liquidity_fee_rune_float * usd_per_rune

            if tx.affiliate_fee > 0:
                aff_fee_usd = tx.get_affiliate_fee_usd(usd_per_rune)
                mark = self._exclamation_sign(aff_fee_usd, 'fee_usd_limit')

                aff_collector = self.name_service.get_affiliate_name(tx.memo.affiliate_address)
                aff_collector = f'{aff_collector} ' if aff_collector else ''

                aff_text = f'{aff_collector}Affiliate fee: {bold(short_dollar(aff_fee_usd))}{mark} ' \
                           f'({format_percent(tx.affiliate_fee, 1)})\n'
            else:
                aff_text = ''

            slip_mark = self._exclamation_sign(l_fee_usd, 'slip_usd_limit')
            content += (
                f"\n{aff_text}"
                f"Slip: {bold(slip_str)}, "
                f"liquidity fee: {bold(short_dollar(l_fee_usd))}{slip_mark}"
            )

            if tx.is_streaming:
                duration = tx.meta_swap.streaming.total_duration
                content += f'\n⏱️ Time elapsed: {self.seconds_human(duration)}.'

                if (success := tx.meta_swap.streaming.success_rate) < 1.0:
                    good = tx.meta_swap.streaming.successful_swaps
                    total = tx.meta_swap.streaming.quantity
                    content += f'\nSuccess rate: {format_percent(success, 1)} ({good}/{total})'

                saved_usd = tx.meta_swap.estimated_savings_vs_cex_usd

                if (saved_usd is not None) and saved_usd > 0.0:
                    content += f'\n🫰Est. Savings vs CEX: {bold(pretty_dollar(saved_usd))}'

        blockchain_components_str = self._add_input_output_links(
            tx, name_map, 'Input: ', 'Output: ', 'User: ')

        msg = f"{heading}\n" \
              f"{blockchain_components_str}\n" \
              f"{content}"

        # todo! cap info
        # if cap:
        #     msg += (
        #         f"\n\n"
        #         f"Liquidity cap is {self._cap_progress_bar(cap)} full now.\n"
        #         f'You can add {code(short_rune(cap.how_much_rune_you_can_lp))} '
        #         f'({short_dollar(cap.how_much_usd_you_can_lp)}) more.\n'
        #     )

        return msg.strip()

    @staticmethod
    def url_for_tx_tracker(tx_id: str):
        return f'https://track.ninerealms.com/{tx_id}'

    def _add_input_output_links(self, tx, name_map, text_inputs, text_outputs, text_user):
        blockchain_components = [f"{text_user}{self.link_to_explorer_user_address_for_tx(tx, name_map)}"]

        if tx.in_tx:
            in_links = self.links_to_txs(tx.in_tx, tx.tx_hash)
            if in_links:
                blockchain_components.append(text_inputs + in_links)
        if tx.out_tx:
            out_links = self.links_to_txs(tx.out_tx, tx.tx_hash)
            if out_links:
                blockchain_components.append(text_outputs + out_links)

        return " / ".join(blockchain_components)

    def get_savers_limits(self, pool: PoolInfo, usd_per_rune, mimir: MimirHolder, asset_amount):
        max_synth_per_asset_ratio = mimir.get_max_synth_per_pool_depth()  # normally: 0.15

        cap = pool.get_synth_cap_in_asset_float(max_synth_per_asset_ratio)
        amount_more = how_much_savings_you_can_add(pool, max_synth_per_asset_ratio)
        saver_pb = self._cap_progress_bar(ThorCapInfo(cap, pool.synth_supply_float, usd_per_rune))
        saver_pct = asset_amount / cap * 100.0 if pool.savers_depth else 100
        return amount_more, Asset(pool.asset).name, saver_pb, cap, saver_pct

    def notification_text_streaming_swap_started(self, e: AlertSwapStart, name_map: NameMap):
        user_link = self.link_to_address(e.from_address, name_map)

        tx_link = link(self.url_for_tx_tracker(e.tx_id), 'Track TX')

        asset_str = Asset(e.in_asset).pretty_str
        amount_str = self.format_op_amount(e.in_amount_float)
        target_asset_str = Asset(e.out_asset).pretty_str
        total_duration_str = self.seconds_human(e.ss.total_duration)

        clout_str = ''
        if e.clout and e.clout.score > 10_000:
            clout_str = f' / {bold(pretty_rune(thor_to_float(e.clout.score)))} clout'

        if e.ss.quantity > 0:
            dur_str = (
                f'{e.ss.quantity} swaps every {e.ss.interval} blocks, '
                f'duration is about {ital(total_duration_str)} + outbound delay.'
            )
        else:
            dur_str = f'Swaps every {e.ss.interval} blocks.'

        return (
            f'🌊 <b>Streaming swap has started</b>\n'
            f'User: {user_link} / {tx_link}{clout_str}\n'
            f'{amount_str} {asset_str} ({short_dollar(e.volume_usd)}) → ⚡ → {bold(target_asset_str)}\n'
            f'{dur_str}'
        )

    # ------- QUEUE -------

    def notification_text_queue_update(self, item_type, is_free, value):
        if is_free:
            return f"☺️ Queue {code(item_type)} is empty again!"
        else:
            if item_type != 'internal':
                extra = f"\n[{item_type}] transactions may be delayed."
            else:
                extra = ''

            return f"🤬 <b>Attention!</b> Queue {code(item_type)} has {value} transactions!{extra}"

    # ------- PRICE -------

    DET_PRICE_HELP_PAGE = 'https://thorchain.org/rune#what-influences-it'

    @property
    def ref_cex_name(self):
        return self.cfg.as_str('price.cex_reference.cex', DEFAULT_CEX_NAME)

    @property
    def ref_cex_pair(self):
        pair = self.cfg.as_str('price.cex_reference.pair', DEFAULT_CEX_BASE_ASSET)
        return f'RUNE/{pair}'

    TEXT_PRICE_NO_DATA = 'Sorry. No price data available yet. Please try again later.'

    def notification_text_price_update(self, p: AlertPrice):
        title = bold('Price update') if not p.is_ath else bold('🚀 A new all-time high has been achieved!')

        c_gecko_url = 'https://www.coingecko.com/en/coins/thorchain'
        c_gecko_link = link(c_gecko_url, 'RUNE')

        message = f"{title} | {c_gecko_link}\n\n"

        if p.halted_chains:
            hc = pre(', '.join(p.halted_chains))
            message += f"🚨 <code>Trading is still halted on {hc}.</code>\n\n"

        price = p.market_info.pool_rune_price

        pr_text = f"${price:.3f}"
        btc_price = f"₿ {p.btc_pool_rune_price:.8f}"
        message += f"<b>RUNE</b> price is {code(pr_text)} ({btc_price}) now.\n"

        fp = p.market_info

        if fp.cex_price > 0.0:
            message += f"<b>RUNE</b> price at {self.ref_cex_name} (CEX) is {code(pretty_dollar(fp.cex_price))} " \
                       f"({self.ref_cex_pair} market).\n"

            div, div_p = fp.divergence_abs, fp.divergence_percent
            exclamation = self._exclamation_sign(div_p, ref=10)
            message += f"<b>Divergence</b> vs CEX is {code(pretty_dollar(div))} ({div_p:.1f}%{exclamation}).\n"

        last_ath = p.last_ath
        if last_ath is not None and p.is_ath:
            last_ath_pr = f'{last_ath.ath_price:.2f}'
            ago_str = self.format_time_ago(now_ts() - last_ath.ath_date)
            message += f"Last ATH was ${pre(last_ath_pr)} ({ago_str}).\n"

        time_combos = zip(
            ('1h', '24h', '7d'),
            (p.price_1h, p.price_24h, p.price_7d)
        )
        for title, old_price in time_combos:
            if old_price:
                pc = calc_percent_change(old_price, price)
                message += code(f"{title.rjust(4)}:{adaptive_round_to_str(pc, True).rjust(8)} % "
                                f"{emoji_for_percent_change(pc).ljust(4).rjust(6)}") + "\n"

        if fp.rank >= 1:
            message += f"Coin market cap is {bold(short_dollar(fp.market_cap))} (#{bold(fp.rank)})\n"

        if fp.total_trade_volume_usd > 0:
            message += f"Total trading volume is {bold(short_dollar(fp.total_trade_volume_usd))}\n"

        message += '\n'

        if fp.tlv_usd >= 1:
            det_link = link(self.DET_PRICE_HELP_PAGE, 'deterministic price')
            message += (f"TVL of non-RUNE assets: {bold(short_dollar(fp.tlv_usd))}\n"
                        f"So {det_link} of RUNE is {code(pretty_dollar(fp.fair_price))}\n"
                        f"Speculative multiplier is {pre(x_ses(fp.fair_price, price))}\n")

        return message.rstrip()

    # ------- POOL CHURN -------

    @staticmethod
    def pool_link(pool_name):
        pool_name = Asset.from_string(pool_name).pretty_str
        return link(get_pool_url(pool_name), pool_name)

    def notification_text_pool_churn(self, pc: PoolChanges):
        if pc.pools_changed:
            message = bold('🏊 Liquidity pool churn!') + '\n\n'
        else:
            message = ''

        def pool_text(pool_name, status, to_status=None, can_swap=True):
            if can_swap and PoolInfo.is_status_enabled(to_status):
                extra = '🎉 <b>BECAME ACTIVE!</b>'
            else:
                extra = ital(status)
                if to_status is not None and status != to_status:  # fix: staged -> staged
                    extra += f' → {ital(to_status)}'
                extra = f'({extra})'
            return f'  • {self.pool_link(pool_name)}: {extra}'

        if pc.pools_added:
            message += '✅ Pools added:\n' + '\n'.join([pool_text(*a) for a in pc.pools_added]) + '\n\n'
        if pc.pools_removed:
            message += ('❌ Pools removed:\n' + '\n'.join([pool_text(*a, can_swap=False) for a in pc.pools_removed])
                        + '\n\n')
        if pc.pools_changed:
            message += '🔄 Pools changed:\n' + '\n'.join([pool_text(*a) for a in pc.pools_changed]) + '\n\n'

        return message.rstrip()

    # -------- SETTINGS --------

    TEXT_SETTING_INTRO = '<b>Settings</b>\nWhat would you like to tune?'
    BUTTON_SET_LANGUAGE = '🌐 Language'
    BUTTON_SET_NODE_OP_GOTO = '🖥️ NodeOp settings'
    BUTTON_SET_PRICE_DIVERGENCE = '↕️ Price divergence'

    BUTTON_RUS = 'Русский'
    BUTTON_ENG = 'English'

    TEXT_SETTINGS_LANGUAGE_SELECT = 'Пожалуйста, выберите язык / Please select a language'

    # ------- PERSONAL PRICE DIVERGENCE -------

    TEXT_PRICE_DIV_MIN_PERCENT = (
        '↕️ Here you can customize your own personal price divergence (CEX vs Native Rune) notifications.\n'
        'For a start, enter a <b>minimum</b> percentage divergence (<i>cannot be less than 0.1</i>).\n'
        'If you don\'t want to be notified on the minimum side, hit "Next"'
    )

    BUTTON_PRICE_DIV_NEXT = 'Next ⏭️'
    BUTTON_PRICE_DIV_TURN_OFF = 'Turn off 📴'

    TEXT_PRICE_DIV_TURNED_OFF = 'Price divergence notifications are turned off.'

    TEXT_PRICE_DIV_MAX_PERCENT = (
        'Good!\n'
        'Now, enter a <b>maximum</b> percentage divergence (<i>cannot be higher than 100</i>).\n'
        'If you don\'t want to be notified on the maximum side, hit "Next"'
    )

    TEXT_PRICE_DIV_INVALID_NUMBER = '<code>Invalid number!</code> Please try again.'

    @staticmethod
    def text_price_div_finish_setup(min_percent, max_percent):
        message = '✔️ Done!\n'
        if min_percent is None and max_percent is None:
            message += '🔘 You will <b>not</b> receive any price divergence notifications.'
        else:
            message += 'Your triggers are\n'
            if min_percent:
                message += f'→ Rune price divergence &lt;= {pretty_money(min_percent)}%\n'
            if max_percent:
                message += f'→ Rune price divergence &gt;= {pretty_money(max_percent)}%\n'
        return message.strip()

    def notification_text_price_divergence(self, info: RuneMarketInfo, is_low: bool):
        title = f'〰️ Low {self.R} price divergence!' if is_low else f'🔺 High {self.R} price divergence!'

        div, div_p = info.divergence_abs, info.divergence_percent
        exclamation = self._exclamation_sign(div_p, ref=10)

        text = (
            f"🖖 {bold(title)}\n"
            f"CEX Rune price is {code(pretty_dollar(info.cex_price))}\n"
            f"Weighted average Rune price by liquidity pools is {code(pretty_dollar(info.pool_rune_price))}\n"
            f"<b>Divergence</b> THORChain vs CEX is {code(pretty_dollar(div))} ({div_p:.1f}%{exclamation})."
        )
        return text

    # -------- METRICS ----------

    BUTTON_METR_S_FINANCIAL = '💱 Financial'
    BUTTON_METR_S_NET_OP = '🔩 Network operation'

    BUTTON_METR_CAP = '✋ Liquidity cap'
    BUTTON_METR_POL = '🥃 POL'
    BUTTON_METR_PRICE = f'💲 {R} price info'
    BUTTON_METR_QUEUE = f'👥 Queue'
    BUTTON_METR_STATS = '📊 Stats'
    BUTTON_METR_NODES = '🖥 Nodes'
    BUTTON_METR_LEADERBOARD = '🏆 Leaderboard'
    BUTTON_METR_SAVERS = '💰 Savers'
    BUTTON_METR_CHAINS = '⛓️ Chains'
    BUTTON_METR_MIMIR = '🎅 Mimir consts'
    BUTTON_METR_VOTING = '🏛️ Voting'
    BUTTON_METR_BLOCK_TIME = '⏱️ Block time'
    BUTTON_METR_TOP_POOLS = '🏊 Top Pools'
    BUTTON_METR_CEX_FLOW = '🌬 CEX Flow'
    BUTTON_METR_SUPPLY = f'🪙 Rune supply'
    BUTTON_METR_DEX_STATS = f'🤹 DEX Aggr. Stats'

    TEXT_METRICS_INTRO = 'What metrics would you like to know?'

    TEXT_QUEUE_PLOT_TITLE = 'THORChain Queue'

    def cap_message(self, info: ThorCapInfo):
        return (
            f"Hello! <b>{short_money(info.pooled_rune)} {self.R}</b> of "
            f"<b>{short_money(info.cap)} {self.R}</b> pooled.\n"
            f"{self._cap_progress_bar(info)}\n"
            f"{self.can_add_more_lp_text(info)}\n"
            f"The {bold(self.R)} price is <code>${info.price:.3f}</code> now.\n"
        )

    def text_leaderboard_info(self):
        return f"🏆 Traders leaderboard is here:\n" \
               f"\n" \
               f" 👉 {bold(URL_LEADERBOARD_MCCN)} 👈\n"

    def queue_message(self, queue_info: QueueInfo):
        return (
            f"<b>Queue info:</b>\n"
            f"- <b>Outbound</b>: {code(queue_info.outbound)} txs {self.queue_to_smile(queue_info.outbound)}\n"
            f"- <b>Swap</b>: {code(queue_info.swap)} txs {self.queue_to_smile(queue_info.swap)}\n"
            f"- <b>Internal</b>: {code(queue_info.internal)} txs {self.queue_to_smile(queue_info.internal)}\n"
        ) + (
            f"If there are many transactions in the queue, your operations may take much longer than usual."
            if queue_info.is_full else ''
        )

    @staticmethod
    def queue_to_smile(n):
        if n <= 3:
            return '🟢'
        elif n <= 20:
            return '🟡'
        elif n <= 50:
            return '🔴'
        else:
            return '🤬❗️'

    TEXT_ASK_DURATION = 'For what period of time do you want to get the data?'

    BUTTON_1_HOUR = '1 hour'
    BUTTON_24_HOURS = '24 hours'
    BUTTON_1_WEEK = '1 week'
    BUTTON_30_DAYS = '30 days'

    # ------- AVATAR -------

    TEXT_AVA_WELCOME = '🖼️ Drop me a picture and I make you THORChain-styled avatar with a gradient frame. ' \
                       'You can send me a picture as a file (or document) to avoid compression issues.'

    TEXT_AVA_ERR_INVALID = '⚠️ Your picture has invalid format!'
    TEXT_AVA_ERR_NO_PIC = '⚠️ You have no user pic...'
    TEXT_AVA_READY = '🥳 <b>Your THORChain avatar is ready!</b> Download this image and set it as a profile picture' \
                     ' at Telegram and other social networks.'

    BUTTON_AVA_FROM_MY_USERPIC = '😀 From my userpic'

    # ------- NETWORK SUMMARY -------

    def network_bond_security_text(self, network_security_ratio):
        if network_security_ratio > 0.9:  # almost no Rune in pools
            return "🥱 INEFFICIENT"
        elif 0.9 >= network_security_ratio > 0.75:
            return "🥸 OVERBONDED"
        elif 0.75 >= network_security_ratio >= 0.6:
            return "⚡ OPTIMAL"
        elif 0.6 > network_security_ratio >= 0.5:  # 0.5 = the same amount of Rune in pools and bonded
            return "🤢 UNDERBONDED"
        elif network_security_ratio == 0.0:
            return '🚧 DATA NOT AVAILABLE...'
        else:
            return "🤬 POTENTIALLY INSECURE"  # more Rune in pools than bonded

    @staticmethod
    def get_network_security_ratio(stats: NetworkStats, nodes: List[NodeInfo]) -> float:
        security_cap = calculate_security_cap_rune(nodes, full=True)

        if not security_cap:
            logging.warning('Security cap is zero!')
            return 0

        divisor = security_cap + stats.total_rune_pooled

        return security_cap / divisor if divisor else 0

    def notification_text_network_summary(self,
                                          old: NetworkStats, new: NetworkStats,
                                          market: RuneMarketInfo,
                                          nodes: List[NodeInfo]):
        message = bold('🌐 THORChain stats') + '\n'

        message += '\n'

        sec_ratio = self.get_network_security_ratio(new, nodes)
        if sec_ratio > 0:
            # security_pb = progressbar(sec_ratio, 1.0, 12)
            security_text = self.network_bond_security_text(sec_ratio)
            message += f'🕸️ Network is now {bold(security_text)}.\n'

        active_nodes_change = bracketify(up_down_arrow(old.active_nodes, new.active_nodes, int_delta=True))
        standby_nodes_change = bracketify(up_down_arrow(old.active_nodes, new.active_nodes, int_delta=True))
        message += f"🖥️ {bold(new.active_nodes)} active nodes {active_nodes_change} " \
                   f"and {bold(new.standby_nodes)} standby nodes {standby_nodes_change}.\n"

        # -- BOND

        current_active_bond_text = bold(short_rune(new.total_active_bond_rune))
        current_active_bond_change = bracketify(
            up_down_arrow(old.total_active_bond_rune, new.total_active_bond_rune, money_delta=True))

        current_bond_usd_text = bold(short_dollar(new.total_active_bond_usd))
        current_bond_usd_change = bracketify(
            up_down_arrow(old.total_active_bond_usd, new.total_active_bond_usd, money_delta=True, money_prefix='$')
        )

        current_total_bond_text = bold(short_rune(new.total_bond_rune))
        current_total_bond_change = bracketify(
            up_down_arrow(old.total_bond_rune, new.total_bond_rune, money_delta=True))

        current_total_bond_usd_text = bold(short_dollar(new.total_bond_usd))
        current_total_bond_usd_change = bracketify(
            up_down_arrow(old.total_bond_usd, new.total_bond_usd, money_delta=True, money_prefix='$')
        )

        message += f"🔗 Active bond: {current_active_bond_text}{current_active_bond_change} or " \
                   f"{current_bond_usd_text}{current_bond_usd_change}.\n"

        message += f"🔗 Total bond including standby: {current_total_bond_text}{current_total_bond_change} or " \
                   f"{current_total_bond_usd_text}{current_total_bond_usd_change}.\n"
        # -- POOL

        current_pooled_text = bold(short_rune(new.total_rune_pooled))
        current_pooled_change = bracketify(
            up_down_arrow(old.total_rune_pooled, new.total_rune_pooled, money_delta=True))

        current_pooled_usd_text = bold(short_dollar(new.total_pooled_usd))
        current_pooled_usd_change = bracketify(
            up_down_arrow(old.total_pooled_usd, new.total_pooled_usd, money_delta=True, money_prefix='$'))

        message += f"🏊 Total pooled: {current_pooled_text}{current_pooled_change} or " \
                   f"{current_pooled_usd_text}{current_pooled_usd_change}.\n"

        # -- LIQ

        current_liquidity_usd_text = bold(short_dollar(new.total_liquidity_usd))
        current_liquidity_usd_change = bracketify(
            up_down_arrow(old.total_liquidity_usd, new.total_liquidity_usd, money_delta=True, money_prefix='$'))

        message += f"🌊 Total liquidity (TVL): {current_liquidity_usd_text}{current_liquidity_usd_change}.\n"

        # -- TVL

        tlv_change = bracketify(
            up_down_arrow(old.total_locked_usd, new.total_locked_usd, money_delta=True, money_prefix='$'))
        message += f'🏦 TVL + Bond: {code(short_dollar(new.total_locked_usd))}{tlv_change}.\n'

        # -- RESERVE

        reserve_change = bracketify(up_down_arrow(old.reserve_rune, new.reserve_rune,
                                                  postfix=RAIDO_GLYPH, money_delta=True))

        message += f'💰 Reserve: {bold(short_rune(new.reserve_rune))}{reserve_change}.\n'

        # --- FLOWS:

        message += '\n'

        if old.is_ok:
            # 24 h Add/withdrawal
            added_24h_rune = new.added_rune - old.added_rune
            withdrawn_24h_rune = new.withdrawn_rune - old.withdrawn_rune
            swap_volume_24h_rune = new.swap_volume_rune - old.swap_volume_rune

            add_rune_text = bold(short_rune(added_24h_rune))
            withdraw_rune_text = bold(short_rune(withdrawn_24h_rune))
            swap_rune_text = bold(short_rune(swap_volume_24h_rune))

            price = new.usd_per_rune

            add_usd_text = short_dollar(added_24h_rune * price)
            withdraw_usd_text = short_dollar(withdrawn_24h_rune * price)
            swap_usd_text = short_dollar(swap_volume_24h_rune * price)

            message += f'{ital("Last 24 hours:")}\n'

            if added_24h_rune:
                message += f'➕ Rune added to pools: {add_rune_text} ({add_usd_text}).\n'

            if withdrawn_24h_rune:
                message += f'➖ Rune withdrawn: {withdraw_rune_text} ({withdraw_usd_text}).\n'

            if swap_volume_24h_rune:
                message += f'🔀 Rune swap volume: {swap_rune_text} ({swap_usd_text}) ' \
                           f'in {bold(short_money(new.swaps_24h))} operations.\n'

            # synthetics:
            synth_volume_rune = code(short_rune(new.synth_volume_24h))
            synth_volume_usd = code(short_dollar(new.synth_volume_24h_usd))
            synth_op_count = short_money(new.synth_op_count)

            message += f'💊 Synth trade volume: {synth_volume_rune} ({synth_volume_usd}) ' \
                       f'in {synth_op_count} swaps.\n'

            # if new.loss_protection_paid_24h_rune:
            #     ilp_rune_str = code(short_rune(new.loss_protection_paid_24h_rune))
            #     ilp_usd_str = code(short_dollar(new.loss_protection_paid_24h_rune * new.usd_per_rune))
            #     message += f'🛡️ IL protection payout: {ilp_rune_str} ({ilp_usd_str}).\n'

            message += '\n'

        bonding_apy_change, liquidity_apy_change = self._extract_apy_deltas(new, old)
        message += f'📈 Bonding APY is {code(pretty_money(new.bonding_apy, postfix="%"))}{bonding_apy_change} and ' \
                   f'Liquidity APY is {code(pretty_money(new.liquidity_apy, postfix="%"))}{liquidity_apy_change}.\n'

        # message += f'🛡️ Total Imp. Loss Protection paid: {code(short_dollar(new.loss_protection_paid_usd))}.\n'

        if new.users_daily or new.users_monthly:
            daily_users_change = bracketify(up_down_arrow(old.users_daily, new.users_daily, int_delta=True))
            monthly_users_change = bracketify(up_down_arrow(old.users_monthly, new.users_monthly, int_delta=True))
            message += f'👥 Daily users: {code(new.users_daily)}{daily_users_change}, ' \
                       f'monthly users: {code(new.users_monthly)}{monthly_users_change} 🆕\n'

        message += '\n'

        active_pool_changes = bracketify(up_down_arrow(old.active_pool_count,
                                                       new.active_pool_count, int_delta=True))
        pending_pool_changes = bracketify(up_down_arrow(old.pending_pool_count,
                                                        new.pending_pool_count, int_delta=True))
        message += f'{bold(new.active_pool_count)} active pools{active_pool_changes} and ' \
                   f'{bold(new.pending_pool_count)} pending pools{pending_pool_changes}.\n'

        if new.next_pool_to_activate:
            next_pool_wait = seconds_human(new.next_pool_activation_ts - now_ts())
            next_pool = self.pool_link(new.next_pool_to_activate)
            message += f"Next pool is likely be activated: {next_pool} in {next_pool_wait}."
        else:
            message += f"There is no eligible pool to be activated yet."

        return message

    @staticmethod
    def _extract_apy_deltas(new, old):
        if abs(old.bonding_apy - new.bonding_apy) > 0.01:
            bonding_apy_change = bracketify(
                up_down_arrow(old.bonding_apy, new.bonding_apy, money_delta=True, postfix=' pp'))
        else:
            bonding_apy_change = ''
        if abs(old.liquidity_apy - new.liquidity_apy) > 0.01:
            liquidity_apy_change = bracketify(
                up_down_arrow(old.liquidity_apy, new.liquidity_apy, money_delta=True, postfix=' pp'))
        else:
            liquidity_apy_change = ''

        return bonding_apy_change, liquidity_apy_change

    TEXT_PIC_STATS_NATIVE_ASSET_VAULTS = "Native Asset Vaults"
    TEXT_PIC_STATS_WEEKLY_REVENUE = "Weekly Protocol Revenue"
    TEXT_PIC_STATS_SWAP_INFO = "Weekly Swap Info"

    TEXT_PIC_STATS_NATIVE_ASSET_POOLED = 'Native Assets Pooled'
    TEXT_PIC_STATS_NETWORK_SECURITY = 'Network Security'
    TEXT_PIC_STATS_PROTOCOL_REVENUE = 'Protocol Revenue'
    TEXT_PIC_STATS_AFFILIATE_REVENUE = 'Affiliate Revenue'
    TEXT_PIC_STATS_TOP_AFFILIATE = 'Top 3 Affiliates by Revenue'
    TEXT_PIC_STATS_UNIQUE_SWAPPERS = 'Unique Swappers'
    TEXT_PIC_STATS_NUMBER_OF_SWAPS = 'Number of Swaps'
    TEXT_PIC_STATS_USD_VOLUME = 'Swap Volume'
    TEXT_PIC_STATS_TOP_SWAP_ROUTES = 'Top 3 Swap Routes'
    TEXT_PIC_STATS_ORGANIC_VS_BLOCK_REWARDS = 'Organic Fees vs Block Rewards'

    @staticmethod
    def text_key_stats_period(start_date: datetime, end_date: datetime):
        date_format = '%d %B %Y'
        return f'{start_date.strftime(date_format)} – {end_date.strftime(date_format)}'

    def notification_text_key_metrics_caption(self, data: AlertKeyStats):
        return 'THORChain weekly stats'

    TEXT_WEEKLY_STATS_NO_DATA = '😩 No data for this period.'

    # ------- NETWORK NODES -------

    TEXT_PIC_NODES = 'nodes'
    TEXT_PIC_ACTIVE_NODES = 'Active nodes'
    TEXT_PIC_STANDBY_NODES = 'Standby nodes'
    TEXT_PIC_ALL_NODES = 'All nodes'
    TEXT_PIC_NODE_DIVERSITY = 'Node Diversity'
    TEXT_PIC_NODE_DIVERSITY_SUBTITLE = 'by infrastructure provider'
    TEXT_PIC_OTHERS = 'Others'
    TEXT_PIC_UNKNOWN = 'Unknown'

    TEXT_PIC_UNKNOWN_LOCATION = 'Unknown location'
    TEXT_PIC_CLOUD = 'Cloud'
    TEXT_PIC_COUNTRY = 'Country'
    TEXT_PIC_ACTIVE_BOND = 'Active bond'
    TEXT_PIC_TOTAL_NODES = 'Total nodes'
    TEXT_PIC_TOTAL_BOND = 'Total bond'
    TEXT_PIC_MIN_BOND = 'Min bond'
    TEXT_PIC_MEDIAN_BOND = 'Median'
    TEXT_PIC_MAX_BOND = 'Max'

    PIC_NODE_DIVERSITY_BY_PROVIDER_CAPTION = ital('THORChain nodes')

    def _format_node_text(self, node: NodeInfo, add_status=False, extended_info=False, expand_link=False):
        if expand_link:
            node_ip_link = link(get_ip_info_link(node.ip_address), node.ip_address) if node.ip_address else 'No IP'
        else:
            node_ip_link = node.ip_address or 'no IP'

        thor_explore_url = get_explorer_url_to_address(self.cfg.network_id, Chains.THOR, node.node_address)
        node_thor_link = link(thor_explore_url, short_address(node.node_address, 0))
        extra = ''
        if extended_info:
            if node.slash_points:
                extra += f', {bold(node.slash_points)} slash points'

            if node.current_award:
                award_text = bold(short_money(node.current_award, postfix=RAIDO_GLYPH))
                extra += f", current award is {award_text}"

        status = f' ({node.status})' if add_status else ''
        version_str = f", v. {node.version}" if extended_info else ''
        return f'{bold(node_thor_link)} ({node.flag_emoji}{node_ip_link}{version_str}) ' \
               f'bond {bold(short_money(node.bond, postfix=RAIDO_GLYPH))} {status}{extra}'.strip()

    def _make_node_list(self, nodes, title, add_status=False, extended_info=False, start=1):
        if not nodes:
            return ''

        message = ''
        if title:
            message += ital(title) + "\n"
        message += join_as_numbered_list(
            (
                self._format_node_text(node, add_status, extended_info)
                for node in nodes if node.node_address
            ),
            start=start
        )
        return message + "\n\n"

    def _node_bond_change_after_churn(self, changes: NodeSetChanges):
        bond_in, bond_out = changes.bond_churn_in, changes.bond_churn_out
        bond_delta = bond_in - bond_out
        return f'Active bond net change: {code(short_money(bond_delta, postfix=RAIDO_GLYPH, signed=True))}'

    def notification_text_node_churn_finish(self, changes: NodeSetChanges):
        message = ''

        if changes.nodes_activated or changes.nodes_deactivated:
            message += bold('♻️ Node churn is complete') + '\n\n'

        message += self._make_node_list(changes.nodes_added, '🆕 New nodes:', add_status=True)
        message += self._make_node_list(changes.nodes_activated, '➡️ Nodes that churned in:')
        message += self._make_node_list(changes.nodes_deactivated, '⬅️️ Nodes that churned out:')
        message += self._make_node_list(changes.nodes_removed, '🗑️ Nodes that disconnected:', add_status=True)

        if changes.nodes_activated or changes.nodes_deactivated:
            message += self._node_bond_change_after_churn(changes)

        if changes.churn_duration:
            message += f'\nChurn duration: {seconds_human(changes.churn_duration)}'

        return message.strip()

    def notification_churn_started(self, changes: NodeSetChanges):
        text = f'♻️ <b>Node churn started at block #{changes.block_no}</b>'
        if changes.vault_migrating:
            text += '\nVaults are migrating.'
        return text

    def node_list_text(self, nodes: List[NodeInfo], status, items_per_chunk=12):
        add_status = False
        if status == NodeInfo.ACTIVE:
            title = '✅ Active nodes:'
            nodes = [n for n in nodes if n.is_active]
        elif status == NodeInfo.STANDBY:
            title = '⏱ Standby nodes:'
            nodes = [n for n in nodes if n.is_standby]
        else:
            title = '❔ Other nodes:'
            nodes = [n for n in nodes if n.in_strange_status]
            add_status = True

        groups = list(grouper(items_per_chunk, nodes))

        starts = []
        current_start = 1
        for group in groups:
            starts.append(current_start)
            current_start += len(group)

        return [
            self._make_node_list(group,
                                 title if start == 1 else '',
                                 extended_info=True,
                                 add_status=add_status,
                                 start=start).rstrip()
            for start, group in zip(starts, groups)
        ]

    # ------ VERSION ------

    @staticmethod
    def node_version(v, data: NodeSetChanges, active=True):
        realm = data.active_only_nodes if active else data.nodes_all
        n_nodes = len(data.find_nodes_with_version(realm, v))
        return f"{code(v)} ({n_nodes} {plural(n_nodes, 'node', 'nodes')})"

    def notification_text_version_upgrade_progress(self,
                                                   data: NodeSetChanges,
                                                   ver_con: NodeVersionConsensus):
        msg = bold('🕖 THORChain version upgrade progress') + '\n\n'

        progress = ver_con.ratio * 100.0
        pb = progressbar(progress, 100.0, 14)

        msg += f'{pb} {progress:.0f} %\n'
        msg += f"{pre(ver_con.top_version_count)} of {pre(ver_con.total_active_node_count)} nodes " \
               f"upgraded to version {pre(ver_con.top_version)}.\n\n"

        cur_version_txt = self.node_version(data.current_active_version, data, active=True)
        msg += f"⚡️ Active protocol version is {cur_version_txt}.\n" + \
               ital('* Minimum version among all active nodes.') + '\n\n'

        return msg

    def notification_text_version_upgrade(self,
                                          data: NodeSetChanges,
                                          new_versions: List[VersionInfo],
                                          old_active_ver: VersionInfo,
                                          new_active_ver: VersionInfo):
        msg = bold('💫 THORChain protocol version update') + '\n\n'

        def version_and_nodes(v, v_all=False):
            realm = data.nodes_all if v_all else data.active_only_nodes
            n_nodes = len(data.find_nodes_with_version(realm, v))
            return f"{code(v)} ({n_nodes} {plural(n_nodes, 'node', 'nodes')})"

        current_active_version = data.current_active_version

        if new_versions:
            new_version_joined = ', '.join(version_and_nodes(v, v_all=True) for v in new_versions)
            msg += f"🆕 New version detected: {new_version_joined}\n\n"

            msg += f"⚡️ Active protocol version is {version_and_nodes(current_active_version)}\n" + \
                   ital('* Minimum version among all active nodes.') + '\n\n'

        if old_active_ver != new_active_ver:
            action = 'upgraded' if new_active_ver > old_active_ver else 'downgraded'
            emoji = '🆙' if new_active_ver > old_active_ver else '⬇️'
            msg += (
                f"{emoji} {bold('Attention!')} Active protocol version has been {bold(action)} "
                f"from {pre(old_active_ver)} "
                f"to {version_and_nodes(new_active_ver)}\n\n"
            )

            cnt = data.version_counter(data.active_only_nodes)
            if len(cnt) == 1:
                msg += f"All active nodes run version {code(current_active_version)}\n"
            elif len(cnt) > 1:
                msg += bold(f"The most popular versions are") + '\n'
                for i, (v, count) in enumerate(cnt.most_common(5), start=1):
                    active_node = ' 👈' if v == current_active_version else ''
                    msg += f"{i}. {version_and_nodes(v)} {active_node}\n"
                msg += f"Maximum version available is {version_and_nodes(data.max_available_version)}\n"

        return msg

    # --------- CHAIN INFO SUMMARY ------------

    def text_chain_info(self, chain_infos: List[ThorChainInfo]):
        text = '⛓️ ' + bold('Chains connected to THORChain') + '\n\n'
        for c in chain_infos:
            address_link = link(get_explorer_url_to_address(self.cfg.network_id, c.chain, c.address), 'SCAN')
            status = '🛑 Halted' if c.halted else '🆗 Active'
            text += f'{bold(c.chain)}:\n' \
                    f'Status: {status}\n' \
                    f'Inbound address: {pre(c.address)} | {address_link}\n'

            if c.router:
                router_link = link(get_explorer_url_to_address(self.cfg.network_id, c.chain, c.router), 'SCAN')
                text += f'Router: {pre(c.router)} | {router_link}\n'

            text += f'Gas rate: {pre(c.gas_rate)}\n\n'

        if not chain_infos:
            text += 'No chain info loaded yet...'

        return text.strip()

    # --------- MIMIR INFO ------------

    MIMIR_DOC_LINK = "https://docs.thorchain.org/how-it-works/governance#mimir"
    MIMIR_ENTRIES_PER_MESSAGE = 20

    MIMIR_STANDARD_VALUE = 'default:'
    MIMIR_OUTRO = f'\n\n🔹 – {ital("Admin Mimir")}\n' \
                  f'🔸 – {ital("Node Mimir")}\n' \
                  f'▪️ – {ital("Automatic solvency checker")}'
    MIMIR_NO_DATA = 'No data'
    MIMIR_BLOCKS = 'blocks'
    MIMIR_DISABLED = 'DISABLED'
    MIMIR_YES = 'YES'
    MIMIR_NO = 'NO'
    MIMIR_UNDEFINED = 'undefined'
    MIMIR_LAST_CHANGE = 'Last change'
    MIMIR_CHEAT_SHEET_URL = 'https://docs.google.com/spreadsheets/d/1mc1mBBExGxtI5a85niijHhle5EtXoTR_S5Ihx808_tM/edit' \
                            '#gid=980980229 '

    MIMIR_UNKNOWN_CHAIN = 'Unknown chain'

    def format_mimir_value(self, name: str, v, units: str = '') -> str:
        if v is None:
            return self.MIMIR_UNDEFINED

        if not units:
            units = MimirUnits.get_mimir_units(name)
            if not units:
                return str(v)

        if units == MimirUnits.UNITS_RUNES:
            return short_money(thor_to_float(v), localization=self.SHORT_MONEY_LOC, postfix=f' {self.R}')
        elif units == MimirUnits.UNITS_BLOCKS:
            blocks = int(v)
            seconds = blocks * THOR_BLOCK_TIME
            time_str = self.seconds_human(seconds) if seconds != 0 else self.MIMIR_DISABLED
            return f'{time_str}, {blocks} {self.MIMIR_BLOCKS}'
        elif units == MimirUnits.UNITS_BOOL:
            s = self.MIMIR_YES if bool(int(v)) else self.MIMIR_NO
            return f'{s}'
        elif units == MimirUnits.UNITS_NEXT_CHAIN:
            try:
                v = int(v)
                chain_name = NEXT_CHAIN_VOTING_MAP.get(v, self.MIMIR_UNKNOWN_CHAIN)
                return f'"{chain_name}"'
            except ValueError:
                return str(v)
        elif units == MimirUnits.UNITS_USD:
            return short_dollar(thor_to_float(v))
        elif units == MimirUnits.UNITS_BASIS_POINTS:
            p = bp_to_percent(v)
            return f'{p:.02f}% ({int(v)} bp)'
        else:
            return str(v)

    def format_mimir_entry(self, i: int, m: MimirEntry):
        if m.source == m.SOURCE_ADMIN:
            mark = '🔹'
        elif m.source == m.SOURCE_NODE:
            mark = '🔸 (consensus) '
        elif m.automatic:
            mark = '▪️'
        else:
            mark = ''

        if m.hard_coded_value is not None:
            std_value_fmt = self.format_mimir_value(m.name, m.hard_coded_value, m.units)
            std_value = f'({self.MIMIR_STANDARD_VALUE} {pre(std_value_fmt)})'
        else:
            std_value = ''

        if m.changed_ts:
            str_ago = self.format_time_ago(now_ts() - m.changed_ts)
            last_change = f'{self.MIMIR_LAST_CHANGE} {ital(str_ago)}'
        else:
            last_change = ''

        real_value_fmt = self.format_mimir_value(m.name, m.real_value, m.units)
        return f'{i}. {mark}{bold(m.pretty_name)} = {code(real_value_fmt)} {std_value} {last_change}'

    def text_mimir_intro(self):
        text = f'🎅 {bold("Global constants and Mimir")}\n'
        cheatsheet_link = link(self.MIMIR_CHEAT_SHEET_URL, 'Cheat sheet')
        what_is_mimir_link = link(self.MIMIR_DOC_LINK, "What is Mimir?")
        text += f"{what_is_mimir_link} And also {cheatsheet_link}.\n\n"
        return text

    def text_mimir_info(self, holder: MimirHolder):
        text_lines = []

        for i, entry in enumerate(holder.all_entries, start=1):
            text_lines.append(self.format_mimir_entry(i, entry))

        lines_grouped = ['\n'.join(line_group) for line_group in grouper(self.MIMIR_ENTRIES_PER_MESSAGE, text_lines)]

        intro, outro = self.text_mimir_intro(), self.MIMIR_OUTRO

        if len(lines_grouped) >= 2:
            messages = [
                intro + lines_grouped[0],
                *lines_grouped[1:-1],
                lines_grouped[-1] + outro
            ]
        elif len(lines_grouped) == 1:
            messages = [intro + lines_grouped[0] + outro]
        else:
            messages = [intro + self.MIMIR_NO_DATA]

        return messages

    NODE_MIMIR_VOTING_GROUP_SIZE = 2
    NEED_VOTES_TO_PASS_MAX = 7

    TEXT_NODE_MIMIR_VOTING_TITLE = '🏛️ <b>Node-Mimir voting</b>\n\n'
    TEXT_NODE_MIMIR_VOTING_NOTHING_YET = 'No active voting yet.'

    TEXT_NODE_MIMIR_ALREADY_CONSENSUS = ' ✅ already consensus'

    def _text_mimir_voting_options(self, holder: MimirHolder,
                                   voting: MimirVoting, options,
                                   triggered_option_value=None):
        message = ''
        name = holder.pretty_name(voting.key)

        n_options = len(options)
        entry = holder.get_entry(voting.key)

        for i, option in enumerate(options, start=1):
            already_consensus = entry and entry.real_value == option.value and entry.source == entry.SOURCE_NODE

            pb = self.make_voting_progress_bar(option, voting)

            extra = f' {pb}{self._text_votes_to_pass(option)}' \
                if not already_consensus else self.TEXT_NODE_MIMIR_ALREADY_CONSENSUS

            pretty_value = self.format_mimir_value(voting.key, str(option.value))
            mark = '👏' if option.value == triggered_option_value else ''
            counter = f"{i}. " if n_options > 1 else ''

            item_name = name
            percent = format_percent(option.number_votes, voting.active_nodes)
            if self.TEXT_DECORATION_ENABLED:
                pretty_value = code(pretty_value)
                percent = bold(percent)
                item_name = bold(name) if i == 1 else name
            message += f"{counter}{item_name} ➔ {pretty_value}: {percent}" \
                       f" ({option.number_votes}/{voting.active_nodes}){mark}{extra}\n"
        return message

    def text_node_mimir_voting(self, holder: MimirHolder):
        title = self.TEXT_NODE_MIMIR_VOTING_TITLE
        if not holder.voting_manager.all_voting:
            title += self.TEXT_NODE_MIMIR_VOTING_NOTHING_YET
            return [title]

        messages = [title]
        for voting in holder.voting_manager.all_voting.values():
            voting: MimirVoting
            msg = self._text_mimir_voting_options(holder, voting, voting.top_options)
            messages.append(msg)

        return regroup_joining(self.NODE_MIMIR_VOTING_GROUP_SIZE, messages)

    def _text_votes_to_pass(self, option):
        show = 0 < option.need_votes_to_pass <= self.NEED_VOTES_TO_PASS_MAX
        return f' {option.need_votes_to_pass} more votes to pass' if show else ''

    TEXT_MIMIR_VOTING_PROGRESS_TITLE = '🏛 <b>Node-Mimir voting update</b>\n\n'
    TEXT_MIMIR_VOTING_TO_SET_IT = 'to set it'

    def notification_text_mimir_voting_progress(self, holder: MimirHolder, key, prev_progress,
                                                voting: MimirVoting,
                                                triggered_option: MimirVoteOption):
        message = self.TEXT_MIMIR_VOTING_PROGRESS_TITLE

        # get up to 3 top options, if there are more options in the voting, add "there are N more..."
        n_options = min(3, len(voting.options))
        message += self._text_mimir_voting_options(holder, voting, voting.top_options[:n_options],
                                                   triggered_option.value if triggered_option else None)
        return message

    @staticmethod
    def make_voting_progress_bar(option: MimirVoteOption, voting: MimirVoting):
        if option.progress > voting.SUPER_MAJORITY:
            return '✅'
        else:
            # if "voting.min_votes_to_pass" (100% == 66.67%), otherwise use "voting.active_nodes"
            if option.progress > 0.12:
                return ' ' + progressbar(option.number_votes, voting.min_votes_to_pass, 12)
            else:
                return ''

    # --------- TRADING HALTED ------------

    def notification_text_trading_halted_multi(self, chain_infos: List[ThorChainInfo]):
        msg = ''

        halted_chains = ', '.join(c.chain for c in chain_infos if c.halted)
        if halted_chains:
            msg += f'🚨🚨🚨 <b>Attention!</b> Trading is halted on the {code(halted_chains)} chain! ' \
                   f'Refrain from using it until the trading is restarted! 🚨🚨🚨\n\n'

        resumed_chains = ', '.join(c.chain for c in chain_infos if not c.halted)
        if resumed_chains:
            msg += f'✅ <b>Heads up!</b> Trading is resumed on the {code(resumed_chains)} chains!'

        return msg.strip()

    # ---------- BLOCK HEIGHT -----------

    TEXT_BLOCK_HEIGHT_CHART_TITLE = 'THORChain block speed'
    TEXT_BLOCK_HEIGHT_LEGEND_ACTUAL = 'Actual blocks/min'
    TEXT_BLOCK_HEIGHT_LEGEND_EXPECTED = 'Expected (10 blocks/min or 6 sec/block)'

    def notification_text_block_stuck(self, e: EventBlockSpeed):
        good_time = e.time_without_blocks is not None and e.time_without_blocks > 1
        str_t = ital(self.seconds_human(e.time_without_blocks) if good_time else self.NA)
        if e.state == BlockProduceState.StateStuck:
            return f'📛 {bold("THORChain block height seems to have stopped increasing")}!\n' \
                   f'New blocks have not been generated for {str_t}.'
        else:
            return f"🆗 {bold('THORChain is producing blocks again!')}\n" \
                   f"The failure lasted {str_t}."

    @staticmethod
    def get_block_time_state_string(state, state_changed):
        if state == BlockProduceState.NormalPace:
            if state_changed:
                return '👌 Block speed is back to normal.'
            else:
                return '👌 Block speed is normal.'
        elif state == BlockProduceState.TooSlow:
            return '🐌 Blocks are being produced too slowly.'
        elif state == BlockProduceState.TooFast:
            return '🏃 Blocks are being produced too fast.'
        else:
            return ''

    def format_bps(self, bps):
        if bps is None:
            return self.ND
        else:
            return f'{float(bps * MINUTE):.2f}'

    def format_block_time(self, bps):
        if bps is None or bps == 0:
            return self.ND
        else:
            sec_per_block = 1.0 / bps
            return f'{float(sec_per_block):.2f}'

    def notification_text_block_pace(self, e: EventBlockSpeed):
        phrase = self.get_block_time_state_string(e.state, True)
        block_per_minute = self.format_bps(e.block_speed)

        return (
            f'<b>THORChain block generation speed update.</b>\n'
            f'{phrase}\n'
            f'Presently <code>{block_per_minute}</code> blocks per minute or '
            f'it takes <code>{self.format_block_time(e.block_speed)} sec</code> to generate a new block.'
        )

    def text_block_time_report(self, last_block, last_block_ts, recent_bps, state):
        phrase = self.get_block_time_state_string(state, False)
        ago = self.format_time_ago(last_block_ts)
        block_str = f"#{last_block}"
        return (
            f'<b>THORChain block generation speed.</b>\n'
            f'{phrase}\n'
            f'Presently <code>{self.format_bps(recent_bps)}</code> blocks per minute or '
            f'it takes <code>{self.format_block_time(recent_bps)} sec</code> to generate a new block.\n'
            f'Last THORChain block number is {code(block_str)} (updated: {ago}).'
        )

    # --------- MIMIR CHANGED -----------

    def notification_text_mimir_changed(self, changes: List[MimirChange], mimir: MimirHolder):
        if not changes:
            return ''

        text = '🔔 <b>Mimir update!</b>\n\n'

        for change in changes:
            old_value_fmt = code(self.format_mimir_value(change.entry.name, change.old_value, change.entry.units))
            new_value_fmt = code(self.format_mimir_value(change.entry.name, change.new_value, change.entry.units))
            name = code(change.entry.pretty_name if change.entry else change.name)

            e = change.entry
            if e:
                if e.source == e.SOURCE_AUTO:
                    text += bold('[🤖 Automatic solvency checker ]  ')
                elif e.source == e.SOURCE_ADMIN:
                    text += bold('[👩‍💻 Admins ]  ')
                elif e.source == e.SOURCE_NODE:
                    text += bold('[🤝 Nodes voted ]  ')
                elif e.source == e.SOURCE_NODE_CEASED:
                    text += bold('[💔 Node-Mimir off ]  ')

            if change.kind == MimirChange.ADDED_MIMIR:
                text += (
                    f'➕ The constant \"{name}\" has been overridden by a new Mimir. '
                    f'The default value was {old_value_fmt} → the new value is {new_value_fmt}‼️'
                )
            elif change.kind == MimirChange.REMOVED_MIMIR:
                text += f"➖ Mimir's constant \"{name}\" has been deleted. It was {old_value_fmt} before. ‼️"
                if change.new_value is not None:
                    text += f" Now this constant reverted to its default value: {new_value_fmt}."
            else:
                text += (
                    f"🔄 Mimir's constant \"{name}\" has been updated from "
                    f"{old_value_fmt} → "
                    f"to {new_value_fmt}‼️"
                )
                if change.entry.automatic and change.non_zero_value:
                    text += f' at block #{ital(change.non_zero_value)}.'
            text += '\n\n'

        text += link(self.MIMIR_DOC_LINK, "What is Mimir?")

        return text

    def joiner(self, fun: callable, items, glue='\n\n'):
        my_fun = getattr(self, fun.__name__)
        return glue.join(map(my_fun, items))

    # ------- NODE OP TOOLS -------

    BUTTON_NOP_ADD_NODES = '➕ Add nodes'
    BUTTON_NOP_MANAGE_NODES = '🖊️ Edit nodes'
    BUTTON_NOP_SETTINGS = '⚙️ Settings'
    BUTTON_NOP_GET_SETTINGS_LINK = '⚙️ New! Web setup'

    @classmethod
    def short_node_name(cls, node_address: str, name=None):
        short_name = node_address[-4:].upper()
        return f'{name} ({short_name})' if name else short_name

    def short_node_desc(self, node: NodeInfo, name=None, watching=False):
        addr = self.short_node_name(node.node_address, name)
        extra = ' ✔️' if watching else ''
        return f'{addr} ({short_money(node.bond, prefix="R")}){extra}'

    def pretty_node_desc(self, node: NodeInfo, name=None):
        addr = self.short_node_name(node.node_address, name)
        return f'{pre(addr)} ({bold(short_money(node.bond, prefix="R"))} bond)'

    TEXT_NOP_INTRO_HEADING = bold('Welcome to the Node Monitor tool!')

    def text_node_op_welcome_text_part2(self, watch_list: list, last_signal_ago: float):
        text = 'It will send you personalized notifications ' \
               'when something important happens to the nodes you are monitoring.\n\n'
        if watch_list:
            text += f'You have {len(watch_list)} nodes in the watchlist.'
        else:
            text += f'You did not add anything to the watch list. Click {ital(self.BUTTON_NOP_ADD_NODES)} first 👇.'

        text += f'\n\nLast signal from the network was {ital(format_time_ago(last_signal_ago))} '
        if last_signal_ago > 60:
            text += '🔴'
        elif last_signal_ago > 20:
            text += '🟠'
        else:
            text += '🟢'

        mon_link = 'https://thorchain.network/'
        text += f'\n\nRealtime monitoring: {link(mon_link, mon_link)}'

        return text

    TEXT_NOP_MANAGE_LIST_TITLE = \
        'You added <b>{n}</b> nodes to your watchlist. ' \
        'Select one in the menu below to stop monitoring the node.'

    TEXT_NOP_ADD_INSTRUCTIONS_PRE = 'Please select the nodes which you would like to add to <b>your watchlist</b> ' \
                                    'from the list below.'

    TEXT_NOP_ADD_INSTRUCTIONS = '🤓 If you know the addresses of the nodes you are interested in, ' \
                                f'just send them to me as a text message. ' \
                                f'You may use the full name {pre("thorAbc5andD1so2on")} or ' \
                                f'the last 3, 4 or more characters. ' \
                                f'Items of the list can be separated by spaces, commas or even new lines.\n\n' \
                                f'Example: {pre("66ew, xqmm, 7nv9")}'
    BUTTON_NOP_ADD_ALL_NODES = 'Add all nodes'
    BUTTON_NOP_ADD_ALL_ACTIVE_NODES = 'Add all ACTIVE nodes'

    TEXT_NOP_SEARCH_NO_VARIANTS = 'No matches found for current search. Please refine your search or use the list.'
    TEXT_NOP_SEARCH_VARIANTS = 'We found the following nodes that match the search:'

    def text_nop_success_add_banner(self, node_addresses):
        node_addresses_text = ','.join([self.short_node_name(a) for a in node_addresses])
        node_addresses_text = shorten_text(node_addresses_text, 80)
        message = f'😉 Success! {node_addresses_text} added to your watchlist. ' \
                  f'Expect notifications of important events.'
        return message

    BUTTON_NOP_CLEAR_LIST = '🗑️ Clear the list ({n})'
    BUTTON_NOP_REMOVE_INACTIVE = '❌ Remove inactive ({n})'
    BUTTON_NOP_REMOVE_DISCONNECTED = '❌ Remove disconnected ({n})'

    def text_nop_success_remove_banner(self, node_addresses):
        node_addresses_text = ','.join([self.short_node_name(a) for a in node_addresses])
        node_addresses_text = shorten_text(node_addresses_text, 120)
        return f'😉 Success! You removed: {node_addresses_text} ({len(node_addresses)} nodes) from your watchlist.'

    TEXT_NOP_SETTINGS_TITLE = 'Tune your notifications here. Choose a topic to adjust settings.'

    def text_nop_get_weblink_title(self, link):
        return f'Your setup link is ready: {link}!\n' \
               f'There you can select the nodes to be monitored and set up notifications.'

    BUTTON_NOP_SETT_OPEN_WEB_LINK = '🌐 Open in Browser'
    BUTTON_NOP_SETT_REVOKE_WEB_LINK = '🤜 Revoke this link'

    TEXT_NOP_REVOKED_URL_SUCCESS = 'Settings URL and token were successfully revoked.'

    BUTTON_NOP_SETT_SLASHING = 'Slashing'
    BUTTON_NOP_SETT_VERSION = 'Version'
    BUTTON_NOP_SETT_OFFLINE = 'Offline'
    BUTTON_NOP_SETT_CHURNING = 'Churning'
    BUTTON_NOP_SETT_BOND = 'Bond'
    BUTTON_NOP_SETT_HEIGHT = 'Block height'
    BUTTON_NOP_SETT_IP_ADDR = 'IP addr.'
    BUTTON_NOP_SETT_PAUSE_ALL = 'Pause all NodeOp alerts'

    @staticmethod
    def text_enabled_disabled(is_on):
        return 'enabled' if is_on else 'disabled'

    def text_nop_slash_enabled(self, is_on):
        en_text = self.text_enabled_disabled(is_on)
        return f'Slash point notifications are {bold(en_text)}.'

    def text_nop_bond_is_enabled(self, is_on):
        en_text = self.text_enabled_disabled(is_on)
        return f'Bond change notifications are {bold(en_text)}.'

    def text_nop_new_version_enabled(self, is_on):
        en_text = self.text_enabled_disabled(is_on)
        return f'New version notifications are {bold(en_text)}.\n\n' \
               f'<i>You will receive a notification when new versions are available.</i>'

    def text_nop_version_up_enabled(self, is_on):
        en_text = self.text_enabled_disabled(is_on)
        return f'Node version upgrade notifications are {bold(en_text)}.\n\n' \
               f'<i>You will receive a notification when your node is upgraded its software.</i>'

    def text_nop_offline_enabled(self, is_on):
        en_text = self.text_enabled_disabled(is_on)
        return f'Offline/online node notifications are {bold(en_text)}.\n\n' \
               f'<i>You can tune enabled services at the next steps.</i>'

    def text_nop_churning_enabled(self, is_on):
        en_text = self.text_enabled_disabled(is_on)
        return f'Churn in/out notifications are {bold(en_text)}.\n\n' \
               f'<i>You will receive a notification when your node churned in or out the active validator set.</i>'

    def text_nop_ip_address_enabled(self, is_on):
        en_text = self.text_enabled_disabled(is_on)
        return f'IP address change notifications are {bold(en_text)}.\n\n' \
               f'<i>You will receive a notification when your node changes its IP address.</i>'

    def text_nop_ask_offline_period(self, current):
        return f'Please tell me the time limit you would like to set for offline notifications. \n\n' \
               f'If there is no connection to your node\'s services for the specified time, ' \
               f'you will receive a message.\n\n' \
               f'Now: {pre(self.seconds_human(current))}.'

    def text_nop_chain_height_enabled(self, is_on):
        en_text = self.text_enabled_disabled(is_on)
        return f'Chain height stuck/unstuck notifications are {bold(en_text)}.\n\n' \
               f'<i>You will receive a notification when any ' \
               f'blockchain client on your node stuck or unstuck scanning blocks.</i>'

    BUTTON_NOP_LEAVE_ON = '✔ Leave it ON'
    BUTTON_NOP_LEAVE_OFF = '✔ Leave it OFF'
    BUTTON_NOP_TURN_ON = 'Turn ON'
    BUTTON_NOP_TURN_OFF = 'Turn OFF'

    BUTTON_NOP_INTERVALS = {
        '2m': '2 min',
        '5m': '5 min',
        '15m': '15 min',
        '30m': '30 min',
        '60m': '60 min',
        '2h': '2 h',
        '6h': '6 h',
        '12h': '12 h',
        '24h': '24 h',
        '3d': '3 days',
    }

    TEXT_NOP_SLASH_THRESHOLD = 'Please select a threshold for slash point ' \
                               'alerts in slash points (recommended around 5 - 10):'

    def text_nop_ask_slash_period(self, pts):
        return f'Great! Please choose a time period for monitoring.\n' \
               f'For example, if you choose <i>10 minutes</i> and a threshold of <i>{pts} pts</i>, ' \
               f'you will get a notification if your node has incurred more than ' \
               f'<i>{pts} slash pts</i> in the last <i>10 minutes</i>.'

    def text_nop_ask_chain_height_lag_time(self, current_lag_time):
        return 'Please select a time interval for the notification threshold. ' \
               'If your node does not scan blocks longer than this time, ' \
               'you will get a notification about it.\n\n' \
               'If the threshold interval is less than the typical block time for the blockchain, ' \
               'it will be increased to 150% of the typical time (15 minutes for BTC).'

    @staticmethod
    def node_link(address):
        short_addr = pre(address[-4:]) if len(address) >= 4 else 'UNKNOWN'
        return link(get_explorer_url_for_node(address), short_addr)

    NODE_OP_MAX_TEXT_MESSAGE_LENGTH = 144

    def notification_text_for_node_op_changes(self, c: NodeEvent):
        message = ''
        short_addr = self.node_link(c.address)
        if c.type == NodeEventType.SLASHING:
            data: EventDataSlash = c.data
            date_str = self.seconds_human(data.interval_sec)
            message = f'🔪 Node {short_addr} got slashed ' \
                      f'for {bold(data.delta_pts)} pts in last ≈{date_str} ' \
                      f'(now it has total <i>{data.current_pts}</i> slash pts)!'
        elif c.type == NodeEventType.VERSION_CHANGED:
            old, new = c.data
            message = f'🆙 Node {short_addr} version upgrade from {ital(old)} to {bold(new)}!'
        elif c.type == NodeEventType.NEW_VERSION_DETECTED:
            message = f'🆕 New version detected! {bold(c.data)}! Consider upgrading!'
        elif c.type == NodeEventType.BOND:
            old, new = c.data
            message = f'⚖️ Node {short_addr}: bond changed ' \
                      f'from {pretty_rune(old)} ' \
                      f'to {bold(pretty_rune(new))}!'
        elif c.type == NodeEventType.IP_ADDRESS_CHANGED:
            old, new = c.data
            message = f'🏤 Node {short_addr} changed its IP address from {ital(old)} to {bold(new)}!'
        elif c.type == NodeEventType.SERVICE_ONLINE:
            online, duration, service = c.data
            service = bold(str(service).upper())
            if online:
                message = f'✅ Service {service} of node {short_addr} is <b>online</b> again!'
            else:
                message = f'🔴 Service {service} of node {short_addr} went <b>offline</b> ' \
                          f'(already for {self.seconds_human(duration)})!'
        elif c.type == NodeEventType.CHURNING:
            verb = 'churned in ⬅️' if c.data else 'churned out ➡️'
            bond = c.node.bond
            message = f'🌐 Node {short_addr} ({short_money(bond)} {RAIDO_GLYPH} bond) {bold(verb)}!'
        elif c.type == NodeEventType.BLOCK_HEIGHT:
            data: EventBlockHeight = c.data

            if data.is_sync:
                message = f'✅ Node {short_addr} caught up blocks for {pre(data.chain)}.'
            else:
                message = f'🔴 Node {short_addr} is {pre(data.block_lag)} blocks behind ' \
                          f'on the {pre(data.chain)} chain (≈{self.seconds_human(data.how_long_behind)})!'
        elif c.type == NodeEventType.PRESENCE:
            if c.data:
                message = f'🙋 Node {short_addr} is back is the THORChain network.'
            else:
                message = f'⁉️ Node {short_addr} has disappeared from the THORChain network.'
        elif c.type == NodeEventType.TEXT_MESSAGE:
            text = str(c.data)[:self.NODE_OP_MAX_TEXT_MESSAGE_LENGTH]
            message = f'⚠️ Message for all: {code(text)}'
        elif c.type == NodeEventType.CABLE_DISCONNECT:
            message = f'💔️ NodeOp tools service has <b>disconnected</b> from THORChain network.\n' \
                      f'Please use an alternative service to monitor nodes until we get it fixed.'
        elif c.type == NodeEventType.CABLE_RECONNECT:
            message = f'💚 NodeOp tools has reconnected to THORChain network.'

        return message

    @staticmethod
    def text_nop_paused_slack(paused, prev_paused, channel_name):
        if paused:
            if prev_paused:
                return f'⏸️ The notification feed is already paused on the channel {channel_name}.\n' \
                       f'Use `/go` command to start it again.'
            else:
                return f'⏸️ The notification feed has been paused on the channel {channel_name}.\n' \
                       f'Use `/go` command to start it again.'
        else:  # running
            if prev_paused:
                return f'▶️ The notification feed has been started on the channel {channel_name}.\n' \
                       f'Use `/pause` command to pause it.'
            else:
                return f'▶️ The notification feed is already running on the channel {channel_name}.\n' \
                       f'Use `/pause` command to pause it.'

    @staticmethod
    def text_nop_settings_link_slack(url, channel_name):
        return f"⚙️ The settings link for the {channel_name} channel is {url}.\n" \
               f"Once set up, you don't need to use any command to start getting notifications."

    TEXT_NOP_NEED_SETUP_SLACK = (
        f'⚠️ First you need to set up the bot. '
        f'Please use `/settings` command to get a personal URL to the channel settings.'
    )

    # ------- BEST POOLS -------

    def format_pool_top(self, attr_name, pd: PoolMapPair, title, no_pool_text, n_pools):
        top_pools = pd.get_top_pools(attr_name, n=n_pools)
        text = bold(title) + '\n'
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

            try:
                if attr_name == pd.BY_APY:
                    delta_p = pretty_money(delta, signed=True, postfix=' pp')
                else:
                    delta_p = pretty_percent(delta)
                delta_p = bracketify(delta_p) if delta else ''
            except ValueError:
                delta_p = ''

            asset = Asset.from_string(pool.asset).shortest
            url = get_pool_url(pool.asset)

            text += f'#{i}. {link(url, asset)}: {code(v)} {delta_p}\n'
        if not top_pools:
            text += no_pool_text
        return text.strip()

    def notification_text_best_pools(self, pd: PoolMapPair, n_pools):
        no_pool_text = 'Nothing yet. Maybe still loading...'
        text = '\n\n'.join([self.format_pool_top(top_pools, pd, title, no_pool_text, n_pools) for title, top_pools in [
            ('💎 Best APY', pd.BY_APY),
            ('💸 Top volume', pd.BY_VOLUME_24h),
            ('🏊 Max Liquidity', pd.BY_DEPTH),
        ]])

        return text

    # ------- INLINE BOT (English only) -------

    INLINE_INVALID_QUERY_TITLE = 'Invalid query!'
    INLINE_INVALID_QUERY_CONTENT = 'Use scheme: <code>@{bot} lp ADDRESS POOL</code>'
    INLINE_INVALID_QUERY_DESC = 'Use scheme: @{bot} lp ADDRESS POOL'
    INLINE_POOL_NOT_FOUND_TITLE = 'Pool not found!'
    INLINE_POOL_NOT_FOUND_TEXT = '{pool}": no such pool.'
    INLINE_INVALID_ADDRESS_TITLE = 'Invalid address!'
    INLINE_INVALID_ADDRESS_TEXT = 'Use THOR or Asset address here.'
    INLINE_LP_CARD = 'LP card of {address} on pool {exact_pool}.'

    INLINE_HINT_HELP_TITLE = 'ℹ️ Help'
    INLINE_HINT_HELP_DESC = 'Use: @{bot} command. Send this to show commands.'
    INLINE_HINT_HELP_CONTENT = (
        'Commands are\n'
        '<code>@{bot} price [1h/24h/7d]</code>\n'
        '<code>@{bot} pools</code>\n'
        '<code>@{bot} stats</code>\n'
        # '<code>@{bot} blocks</code>\n'  # todo
        # '<code>@{bot} queue</code>\n'  # todo
        '<code>@{bot} lp ADDRESS POOL</code>\n'
    )

    INLINE_INTERNAL_ERROR_TITLE = 'Internal error!'
    INLINE_INTERNAL_ERROR_CONTENT = f'Sorry, something went wrong! Please report it to {CREATOR_TG}.'

    INLINE_TOP_POOLS_TITLE = '🏊 THORChain Top Pools'
    INLINE_TOP_POOLS_DESC = 'Top 5 by APY, volume and liquidity'

    INLINE_STATS_TITLE = '📊 THORChain Statistics'
    INLINE_STATS_DESC = 'Last 24h summary of key stats'

    # ---- MISC ----

    def format_time_ago(self, d):
        return format_time_ago(d)

    def seconds_human(self, s):
        return seconds_human(s)

    # ----- FLOW ------

    @staticmethod
    def cex_flow_emoji(cex_flow: RuneCEXFlow):
        limit = 1000.0
        return '🟢' if cex_flow.netflow_usd < -limit else ('🔴' if cex_flow.netflow_usd > limit else '⚪️')

    def notification_text_cex_flow(self, cex_flow: RuneCEXFlow):
        emoji = self.cex_flow_emoji(cex_flow)
        period_string = self.format_period(cex_flow.period_sec)
        return (f'🌬️ <b>Rune CEX flow last {period_string}</b>\n'
                f'➡️ Inflow: {pre(short_money(cex_flow.rune_cex_inflow, postfix=RAIDO_GLYPH))} '
                f'({short_dollar(cex_flow.in_usd)})\n'
                f'⬅️ Outflow: {pre(short_money(cex_flow.rune_cex_outflow, postfix=RAIDO_GLYPH))} '
                f'({short_dollar(cex_flow.out_usd)})\n'
                f'{emoji} Netflow: {pre(short_money(cex_flow.rune_cex_netflow, postfix=RAIDO_GLYPH, signed=True))} '
                f'({short_dollar(cex_flow.netflow_usd)})')

    # ----- SUPPLY ------

    def text_metrics_supply(self, market_info: RuneMarketInfo):
        sp = market_info.supply_info

        burn_amt = short_rune(abs(sp.lending_burnt_rune))
        burn_pct = format_percent(abs(sp.lending_burnt_rune), sp.total)
        if sp.lending_burnt_rune > 0:
            str_burnt = f'🔥 Burnt Rune (<b>lending</b>) are {code(burn_amt)} ({burn_pct})!\n'
        elif sp.lending_burnt_rune < 0:
            str_burnt = f'🪙 Minted Rune are {burn_amt} ({burn_pct})\n'
        else:
            str_burnt = ''

        return (
            f'⚡️Rune supply is {pre(pretty_rune(market_info.total_supply))}\n'
            f'{str_burnt}'
            f'🏊‍ {pre(short_rune(sp.pooled))} ({format_percent(sp.pooled_percent)}) are pooled\n'
            f'🔒 {pre(short_rune(sp.bonded))} ({format_percent(sp.bonded_percent)}) are bonded\n'
            f'🏦 {pre(short_rune(sp.in_cex))} ({format_percent(sp.in_cex_percent, )}) are in CEX\n'
            f'💰 Treasury has {pre(pretty_rune(sp.treasury))}'
        )

    SUPPLY_PIC_CIRCULATING = 'Other circulating'
    SUPPLY_PIC_RESERVES = ThorRealms.RESERVES
    SUPPLY_PIC_UNDEPLOYED = ThorRealms.STANDBY_RESERVES
    SUPPLY_PIC_BONDED = 'Bond'
    SUPPLY_PIC_TREASURY = 'Treasury'
    SUPPLY_PIC_MAYA = 'Maya pool'
    SUPPLY_PIC_POOLED = ThorRealms.POOLED
    SUPPLY_PIC_BURNED = ThorRealms.BURNED
    SUPPLY_PIC_SECTION_CIRCULATING = 'THOR.RUNE circulating'
    SUPPLY_PIC_SECTION_LOCKED = 'THOR.RUNE locked'
    SUPPLY_PIC_SECTION_KILLED = 'Killed switched'

    SUPPLY_PIC_CAPTION = ital('THORChain Rune supply chart')

    # ---- MY WALLET ALERTS ----

    @staticmethod
    def _is_my_address_tag(address, my_addresses):
        return ' ★' if my_addresses and address in my_addresses else ''

    def link_to_address(self, addr, name_map, chain=Chains.THOR):
        url = get_explorer_url_to_address(self.cfg.network_id, chain, addr)
        name = name_map.by_address.get(addr)
        caption = add_thor_suffix(name) if name else short_address(addr)
        return link(url, caption)

    def _native_transfer_prepare_stuff(self, my_addresses, t: RuneTransfer, tx_title='TX', name_map=None):
        my_addresses = my_addresses or []
        name_map = name_map or {}

        # USD value
        if t.usd_per_asset:
            usd_amt = f' ({pretty_dollar(t.usd_amount)})'
        else:
            usd_amt = ''

        # Addresses
        from_my = self.link_to_address(t.from_addr, name_map) + self._is_my_address_tag(t.from_addr, my_addresses)
        to_my = self.link_to_address(t.to_addr, name_map) + self._is_my_address_tag(t.to_addr, my_addresses)

        # Comment
        comment = ''
        if t.comment:
            comment = shorten_text(t.comment, 100)
            if comment.startswith('Msg'):
                comment = comment[3:]
            comment = f' "{comment.capitalize()}"'

        # TX link
        if t.tx_hash:
            tx_title = tx_title or comment
            tx_link = ' ' + link(get_explorer_url_to_tx(self.cfg.network_id, Chains.THOR, t.tx_hash), tx_title)
        else:
            tx_link = ''

        # Asset name
        asset = Asset.from_string(t.asset).pretty_str

        memo = ''
        if t.memo and not t.memo.startswith('OUT:'):
            memo = f' MEMO: "{code(shorten_text(t.memo, limit=42))}"'

        return asset, comment, from_my, to_my, tx_link, usd_amt, memo

    def notification_text_rune_transfer(self, t: RuneTransfer, my_addresses, name_map):
        asset, comment, from_my, to_my, tx_link, usd_amt, memo = self._native_transfer_prepare_stuff(
            my_addresses, t,
            name_map=name_map
        )

        return f'🏦 <b>{comment}</b>{tx_link}: {code(short_money(t.amount, postfix=" " + asset))}{usd_amt} ' \
               f'from {from_my} ' \
               f'➡️ {to_my}{memo}.'

    def notification_text_rune_transfer_public(self, t: RuneTransfer, name_map: NameMap):
        asset, comment, from_my, to_my, tx_link, usd_amt, memo = self._native_transfer_prepare_stuff(
            None, t,
            tx_title='',
            name_map=name_map
        )

        return f'💸 <b>Large transfer</b>{tx_link}: ' \
               f'{code(short_money(t.amount, postfix=" " + asset))}{usd_amt} ' \
               f'from {from_my} ➡️ {to_my}{memo}.'

    def notification_text_regular_lp_report(self, user, address, pool, lp_report: LiquidityPoolReport, local_name: str,
                                            unsub_id):
        explorer_link, name_str, pretty_pool, thor_yield_link = self._regular_report_variables(address, local_name,
                                                                                               pool)

        pos_type = 'savings' if lp_report.is_savers else 'liquidity'
        return (
            f'Your {pos_type} position report {explorer_link}{name_str} in the pool {pre(pretty_pool)} is ready.\n'
            f'{thor_yield_link}.\n\n'
            f'Unsubscribe /unsub_{unsub_id}'
        )

    def _regular_report_variables(self, address, local_name, pool):
        pool_asset = Asset(pool)
        pretty_pool = pool_asset.l1_asset.pretty_str
        explorer_url = get_explorer_url_to_address(self.cfg.network_id, Chains.THOR, address)
        explorer_link = link(explorer_url, short_address(address, 10, 5))
        thor_yield_url = get_thoryield_address(self.cfg.network_id, address)
        thor_yield_link = link(thor_yield_url, 'THORYield')
        name_str = f' ({ital(local_name)})' if local_name else ''

        return explorer_link, name_str, pretty_pool, thor_yield_link

    # ------ DEX -------

    @staticmethod
    def format_dex_entry(e: DexReportEntry, r):
        n = e.count
        txs = 'tx' if n == 1 else 'txs'
        return (
            f'{bold(n)} {txs} '
            f'({pre(short_rune(e.rune_volume))} or '
            f'{pre(short_dollar(e.rune_volume * r.usd_per_rune))})')

    STR_24_HOUR = '24h'

    def format_period(self, period: float):
        period = float(period)
        if period == DAY:
            return self.STR_24_HOUR
        else:
            return self.seconds_human(period)

    def notification_text_dex_report(self, r: DexReport):
        period_str = self.format_period(r.period_sec)

        top_aggr = r.top_popular_aggregators()[:3]
        top_aggr_str = ''
        for i, (_, e) in enumerate(top_aggr, start=1):
            e: DexReportEntry
            top_aggr_str += f'{i}. {code(e.name)}: {self.format_dex_entry(e, r)} \n'
        top_aggr_str = top_aggr_str or '-'

        top_asset_str = ''
        top_asset = r.top_popular_assets()[:3]
        for i, (_, e) in enumerate(top_asset, start=1):
            e: DexReportEntry
            top_asset_str += f'{i}. {code(e.name)}: {self.format_dex_entry(e, r)} \n'
        top_asset_str = top_asset_str or '-'

        return (
            f'🤹🏻‍♂️ <b>DEX aggregator usage last {period_str}</b>\n\n'
            f'→ Swap In: {self.format_dex_entry(r.swap_ins, r)}\n'
            f'← Swap Out: {self.format_dex_entry(r.swap_outs, r)}\n'
            f'∑ Total: {self.format_dex_entry(r.total, r)}\n\n'
            f'Popular aggregators:\n{top_aggr_str}\n'
            f'Popular assets:\n{top_asset_str}'
        ).strip()

    # ------ SAVERS -------

    MIN_PERCENT_TO_SHOW_VAULT_FILL = 10

    def notification_text_saver_stats(self, event: AlertSaverStats):
        message = f'💰 <b>THORChain Savers Vaults summary</b>\n'

        savers, prev = event.current_stats, event.previous_stats

        total_earned_usd = savers.total_rune_earned * event.price_holder.usd_per_rune
        avg_apr_change, saver_number_change, total_earned_change_usd, total_usd_change = \
            self.get_savers_stat_changed_metrics_as_str(event, prev, savers, total_earned_usd)

        fill_cap = savers.overall_fill_cap_percent(event.price_holder.pool_info_map)

        message += (
            f'\n'
            f'Total {code(savers.total_unique_savers)}{saver_number_change} savers '
            f'with {code(short_dollar(savers.total_usd_saved))}{total_usd_change} saved.\n'
            f'<b>Average APR</b> is {pre(pretty_money(savers.average_apr))}%{avg_apr_change}.\n'
            f'Total earned: {pre(pretty_dollar(total_earned_usd))}{total_earned_change_usd}.\n'
            f'Total filled: {fill_cap:.1f}%'
        )

        return message

    @staticmethod
    def get_savers_stat_changed_metrics_as_str(event: AlertSaverStats, prev, savers, total_earned_usd):
        if prev:
            saver_number_change = bracketify(up_down_arrow(
                prev.total_unique_savers, savers.total_unique_savers, int_delta=True), before=' ')
            total_usd_change = bracketify(up_down_arrow(
                prev.total_usd_saved, savers.total_usd_saved, money_delta=True, money_prefix='$'), before=' ')
            avg_apr_change = bracketify(up_down_arrow(
                prev.average_apr, savers.average_apr, money_delta=True, postfix='%'
            ), before=' ')
            prev_total_earned_usd = prev.total_rune_earned * event.price_holder.usd_per_rune
            total_earned_change_usd = bracketify(up_down_arrow(
                prev_total_earned_usd, total_earned_usd, money_delta=True, money_prefix='$'
            ), before=' ')
        else:
            saver_number_change = ''
            total_usd_change = ''
            avg_apr_change = ''
            total_earned_change_usd = ''
        return avg_apr_change, saver_number_change, total_earned_change_usd, total_usd_change

    TEXT_PIC_SAVERS_VAULTS = 'savers vaults'
    TEXT_PIC_SAVERS_TOTAL_SAVERS = 'Total Savers'
    TEXT_PIC_SAVERS_TOTAL_SAVED_VALUE = 'Total Saved Value'
    TEXT_PIC_SAVERS_TOTAL_EARNED = 'Total Earned'
    TEXT_PIC_SAVERS_APR_MEAN = 'APR Mean'
    TEXT_PIC_SAVERS_TOTAL_FILLED = 'Total Filled'
    TEXT_PIC_SAVERS_OR = ' or '
    TEXT_PIC_SAVERS_ASSET = 'Asset'
    TEXT_PIC_SAVERS_USD = 'USD'
    TEXT_PIC_SAVERS_APR = 'APR'
    TEXT_PIC_SAVERS = 'Savers'
    TEXT_PIC_SAVERS_FILLED = 'Savers filled'
    TEXT_PIC_SAVERS_EARNED = 'Earned'

    TEXT_SAVERS_NO_DATA = '😩 Sorry. We have not gotten any data for Savers Vaults yet.'

    SV_PIC_TITLE = 'savings'
    SV_PIC_APR = 'APR'
    SV_PIC_USD = 'USD'
    SV_PIC_ADDED = 'Added'
    SV_PIC_WITHDRAWN = 'Withdrawn'
    SV_PIC_REDEEMABLE = 'Redeemable'
    SV_PIC_PRICE = 'Price'
    SV_PIC_EARNED = 'Earned'
    SV_PIC_ELAPSED = 'elapsed since addition'

    # ------ POL -------

    @staticmethod
    def pretty_asset(name):
        return Asset(name).pretty_str

    def _format_pol_membership(self, event: AlertPOL, of_pool, decor=True):
        text = ''
        for i, details in enumerate(event.membership, start=1):
            pool: PoolInfo = event.prices.find_pool(details.pool)
            rune = pool.total_my_capital_of_pool_in_rune(details.liquidity_units)
            share = pool.percent_share(rune)
            usd = rune * event.prices.usd_per_rune
            asset = self.pretty_asset(details.pool)
            val = short_rune(rune)
            pool_pct = pretty_percent(share, signed=False)
            if decor:
                val = pre(val)
            text += (
                f'‣ {asset}: {val} ({short_dollar(usd)}),'
                f' {pool_pct} {of_pool}\n'
            )
        return text.strip()

    def notification_text_pol_utilization(self, event: AlertPOL):
        text = '🥃 <b>Protocol Owned Liquidity</b>\n\n'

        curr, prev = event.current, event.previous
        pol_progress = progressbar(curr.rune_value, event.mimir_max_deposit, 10)

        str_value_delta_pct, str_value_delta_abs = '', ''
        if prev:
            str_value_delta_pct = up_down_arrow(prev.rune_value, curr.rune_value, percent_delta=True, brackets=True,
                                                threshold_pct=0.5)
            # str_value_delta_abs = up_down_arrow(
            # prev.rune_value, curr.rune_value, money_delta=True, postfix=RAIDO_GLYPH)

        pnl_pct = curr.pnl_percent
        text += (
            f"Current POL value: {code(short_rune(curr.rune_value))} or "
            f" {code(short_dollar(curr.usd_value))} {str_value_delta_pct}\n"
            f"POL utilization: {pre(pretty_percent(event.pol_utilization, signed=False))} {pre(pol_progress)} "
            f" of {short_rune(event.mimir_max_deposit)} maximum.\n"
            f"Rune deposited: {pre(short_rune(curr.rune_deposited))}, "
            f"withdrawn: {pre(short_rune(curr.rune_withdrawn))}\n"
            f"Profit and Loss: {pre(pretty_percent(pnl_pct))} {chart_emoji(pnl_pct)}"
        )

        # POL pool membership
        if event.membership:
            text += "\n\n<b>Pool membership:</b>\n"
            text += self._format_pol_membership(event, of_pool='of pool')

        return text.strip()

    # ----- LOANS ------
    LENDING_DASHBOARD_URL = 'https://dashboards.ninerealms.com/#lending'

    def notification_text_loan_open(self, event: AlertLoanOpen, name_map: NameMap):
        l = event.loan
        user_link = self.link_to_address(l.owner, name_map)
        asset = ' ' + Asset(l.collateral_asset).pretty_str
        target_asset = Asset(l.target_asset).pretty_str
        db_link = link(self.LENDING_DASHBOARD_URL, "Dashboard")
        # tx_link = link(get_explorer_url_to_tx(self.cfg.network_id, Chains.THOR, event.tx_id), "TX")
        return (
            '🏦→ <b>Loan open</b>\n'
            f'Collateral deposited: {code(pretty_money(l.collateral_float, postfix=asset))}'
            f' ({pretty_dollar(event.collateral_usd)})\n'
            f'CR: x{pretty_money(l.collateralization_ratio)}\n'
            f'Debt: {code(pretty_dollar(l.debt_usd))}\n'
            f'Target asset: {pre(target_asset)}\n'
            f'{user_link} | {db_link}'
        )

    def notification_text_loan_repayment(self, event: AlertLoanRepayment, name_map: NameMap):
        user_link = self.link_to_address(event.loan.owner, name_map)
        asset = ' ' + Asset(event.loan.collateral_asset).pretty_str
        db_link = link(self.LENDING_DASHBOARD_URL, "Dashboard")
        # tx_link = link(get_explorer_url_to_tx(self.cfg.network_id, Chains.THOR, event.tx_id), "TX")
        return (
            '🏦← <b>Loan repayment</b>\n'
            f'Collateral withdrawn: {code(pretty_money(event.loan.collateral_float, postfix=asset))}'
            f' ({pretty_dollar(event.collateral_usd)})\n'
            f'Debt repaid: {pre(pretty_dollar(event.loan.debt_repaid_usd))}\n'
            f'{user_link} | {db_link}'
        )

    LENDING_LINK = "https://flipsidecrypto.xyz/banbannard/%E2%9A%A1-thor-chain-lending-thorchain-lending-fOAKej"

    def notification_lending_stats(self, event: AlertLendingStats):
        curr = event.current
        return (
            f'<b>Lending stats</b>\n\n'
            f'🙋‍♀️ Borrower count: {bold(pretty_money(curr.borrower_count))}\n'
            f'📝 Lending Tx count: {bold(pretty_money(curr.lending_tx_count))}\n'
            f'💰 Total collateral value: {bold(short_dollar(curr.total_collateral_value_usd))}\n'
            f'💸 Total borrowed value: {bold(short_dollar(curr.total_borrowed_amount_usd))}\n'
            f'₿ Bitcoin CR: {bold(short_money(curr.btc_current_cr))}, '
            f'LTV: {bold(short_money(curr.btc_current_ltv))}\n'
            f'Ξ Ethereum CR: {bold(short_money(curr.eth_current_cr))}, '
            f'LTV: {bold(short_money(curr.eth_current_ltv))}\n'
            f'❤️‍🔥 Rune burned: {bold(short_rune(curr.rune_burned_rune))}\n\n'
            f'{link(self.LENDING_LINK, "Details")}'
        )

    # ------ Bond providers alerts ------

    TEXT_BOND_PROVIDER_ALERT_FOR = 'Alert for bond provider'
    TEXT_BP_NODE = '🖥️ Node'

    def notification_text_bond_provider_alert(self, bp_to_node_to_event, name_map: NameMap):
        message = ''
        for bp_address, nodes in bp_to_node_to_event.items():
            bp_link = '👤' + self.link_to_address(bp_address, name_map)
            message += f'🔔 <b>{self.TEXT_BOND_PROVIDER_ALERT_FOR} {bp_link}</b>\n'

            for node_address, events in nodes.items():
                message += f' └ {self.TEXT_BP_NODE} {self.link_to_address(node_address, name_map)}\n'
                for event in events:
                    message += f"      └ {self.bond_provider_event_text(event)}\n"

            message += '\n'

        return message

    def bp_event_duration(self, ev: EventProviderStatus):
        dur = ev.duration
        return f' ({self.seconds_human(dur)} since last status)' if dur else ''

    @staticmethod
    def bp_bond_percent(ev: EventProviderBondChange):
        if ev.prev_bond <= 0:
            return 0
        return format_percent(ev.curr_bond - ev.prev_bond, ev.prev_bond, signed=True)

    def bond_provider_event_text(self, event: NodeEvent):
        if event.type == NodeEventType.FEE_CHANGE:
            verb = 'has raised' if event.data.previous < event.data.current else 'has dropped'
            return (
                f'％ The node operator {ital(verb)} the fee from '
                f'{pre(format_percent(event.data.previous, 1))} to {pre(format_percent(event.data.current, 1))}.'
            )
        elif event.type == NodeEventType.CHURNING:
            data: EventProviderStatus = event.data
            emoji = '✳️' if data.appeared else '⏳'
            verb = 'churned in' if data.appeared else 'churned out'
            return f'{emoji} The node has {bold(verb)}{self.bp_event_duration(data)}.'
        elif event.type == NodeEventType.PRESENCE:
            data: EventProviderStatus = event.data
            verb = 'connected' if data.appeared else 'disconnected'
            emoji = '✅' if data.appeared else '❌'
            return f'{emoji} The node has {bold(verb)}{self.bp_event_duration(data)}!'
        elif event.type == NodeEventType.BOND_CHANGE:
            data: EventProviderBondChange = event.data
            delta = data.curr_bond - data.prev_bond
            delta_str = up_down_arrow(data.prev_bond, data.curr_bond, money_delta=True, postfix=RAIDO_GLYPH)
            verb = 'increased' if delta > 0 else 'decreased'
            emoji = '📈' if delta > 0 else '📉'
            return (
                f'{emoji} Bond amount has {bold(verb)} '
                f'from {pre(pretty_rune(data.prev_bond))} '
                f'to {pre(pretty_rune(data.curr_bond))} '
                f'({ital(delta_str)} or {ital(self.bp_bond_percent(data))}).'
            )
        elif event.type == NodeEventType.BP_PRESENCE:
            data: EventProviderStatus = event.data
            verb = 'appeared on' if data.appeared else 'disappeared from'
            emoji = '🙅' if data.appeared else '👌'
            return f'{emoji} The address has {ital(verb)} the bond provider list of the node' \
                   f'{self.bp_event_duration(data)}.'
        else:
            return ''


class EnglishLocalization(BaseLocalization):
    # it is already English!
    ...
