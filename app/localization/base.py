from abc import ABC
from datetime import datetime
from math import ceil

from services.lib.config import Config
from services.lib.constants import NetworkIdents
from services.lib.date_utils import format_time_ago, now_ts, seconds_human
from services.lib.explorers import get_explorer_url_to_address, Chains, get_explorer_url_to_tx
from services.lib.money import format_percent, asset_name_cut_chain, pretty_money, short_address, short_money, \
    short_asset_name, calc_percent_change, adaptive_round_to_str, pretty_dollar, emoji_for_percent_change, \
    chain_name_from_pool
from services.lib.texts import progressbar, kbd, link, pre, code, bold, x_ses, ital, BoardMessage, \
    link_with_domain_text, up_down_arrow, bracketify
from services.models.cap_info import ThorCapInfo
from services.models.net_stats import NetworkStats
from services.models.pool_info import PoolInfo
from services.models.price import RuneFairPrice, PriceReport
from services.models.queue import QueueInfo
from services.models.tx import LPAddWithdrawTx, ThorTxType
from services.models.pool_stats import StakePoolStats

RAIDO_GLYPH = 'ᚱ'
CREATOR_TG = '@account1242'

BEP2_SWAP = 'https://chaosnet.bepswap.com/'
THOR_SWAP = 'https://app.thorswap.finance/'


class BaseLocalization(ABC):  # == English
    def __init__(self, cfg: Config):
        self.cfg = cfg

    # ----- WELCOME ------

    @property
    def this_bot_name(self):
        return self.cfg.telegram.bot.username

    @property
    def url_start_me(self):
        return f'https://telegram.me/{self.this_bot_name}?start=1'

    @property
    def alert_channel_name(self):
        return self.cfg.telegram.channels[0]['name']

    @staticmethod
    def thor_explore_address(address):
        return f'https://viewblock.io/thorchain/address/{address}'

    @staticmethod
    def binance_explore_address(address):
        return f'https://explorer.binance.org/address/{address}'

    @staticmethod
    def _cap_progress_bar(info: ThorCapInfo):
        return f'{progressbar(info.stacked, info.cap, 10)} ({format_percent(info.stacked, info.cap)})\n'

    # ---- WELCOME ----
    def help_message(self):
        return (
            f"This bot is for {link(self.THORCHAIN_LINK, 'THORChain')} monitoring.\n"
            f"Command list:\n"
            f"/help – this help page\n"
            f"/start – start/restart the bot\n"
            f"/lang – set the language\n"
            f"/cap – the current liquidity cap of Chaosnet\n"
            f"/price – the current Rune price.\n"
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

    BUTTON_RUS = 'Русский'
    BUTTON_ENG = 'English'

    THORCHAIN_LINK = 'https://thorchain.org/'

    R = 'Rune'

    def lang_help(self):
        return (
            f'Пожалуйста, выберите язык / Please select a language',
            kbd([self.BUTTON_RUS, self.BUTTON_ENG], one_time=True)
        )

    def unknown_command(self):
        return (
            "🙄 Sorry, I didn't understand that command.\n"
            "Use /help to see available commands."
        )

    # ----- MAIN MENU ------

    BUTTON_MM_MY_ADDRESS = '🏦 Manage my address'
    BUTTON_MM_METRICS = '📐 Metrics'
    BUTTON_MM_SETTINGS = f'⚙️ Settings'
    BUTTON_MM_MAKE_AVATAR = f'🦹‍️️ THOR Avatar'

    def kbd_main_menu(self):
        return kbd([
            [self.BUTTON_MM_MY_ADDRESS, self.BUTTON_MM_METRICS],
            [self.BUTTON_MM_MAKE_AVATAR, self.BUTTON_MM_SETTINGS]
        ])

    # ------- STAKE INFO MENU -------

    BUTTON_SM_ADD_ADDRESS = '➕ Add an address'
    BUTTON_BACK = '🔙 Back'
    BUTTON_SM_BACK_TO_LIST = '🔙 Back to list'
    BUTTON_SM_BACK_MM = '🔙 Main menu'

    BUTTON_SM_SUMMARY = '💲 Summary'

    BUTTON_VIEW_RUNESTAKEINFO = '🌎 View it on runeyield.info'
    BUTTON_VIEW_VALUE_ON = 'Show value: ON'
    BUTTON_VIEW_VALUE_OFF = 'Show value: OFF'
    BUTTON_REMOVE_THIS_ADDRESS = '❌ Remove this address'

    TEXT_NO_ADDRESSES = "🔆 You have not added any addresses yet. Send me one."
    TEXT_YOUR_ADDRESSES = '🔆 You added addresses:'
    TEXT_INVALID_ADDRESS = code('⛔️ Invalid address!')
    TEXT_SELECT_ADDRESS_ABOVE = 'Select one from above. ☝️ '
    TEXT_SELECT_ADDRESS_SEND_ME = 'If you want to add one more, please send me it. 👇'
    TEXT_LP_NO_POOLS_FOR_THIS_ADDRESS = "📪 <b>This address doesn't participate in any liquidity pools.</b> " \
                                        "Please choose another one or add new."

    def text_lp_img_caption(self):
        bot_link = "@" + self.this_bot_name
        start_me = self.url_start_me
        return f'Generated by {link(start_me, bot_link)}'

    LP_PIC_POOL = 'POOL'
    LP_PIC_RUNE = 'RUNE'
    LP_PIC_ADDED = 'Added'
    LP_PIC_WITHDRAWN = 'Withdrawn'
    LP_PIC_REDEEM = 'Redeemable'
    LP_PIC_GAIN_LOSS = 'Gain / Loss'
    LP_PIC_IN_USD = 'in USD'
    LP_PIC_R_RUNE = f'{RAIDO_GLYPH}une'
    LP_PIC_ADDED_VALUE = 'Added value'
    LP_PIC_WITHDRAWN_VALUE = 'Withdrawn value'
    LP_PIC_CURRENT_VALUE = 'Current value'
    LP_PIC_PRICE_CHANGE = 'Price change'
    LP_PIC_PRICE_CHANGE_2 = 'since the first addition'
    LP_PIC_LP_VS_HOLD = 'LP vs HOLD'
    LP_PIC_LP_APY = 'LP APY'
    LP_PIC_EARLY = 'Early...'
    LP_PIC_FOOTER = ""
    LP_PIC_FEES = 'Fees earned'

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

    def pic_stake_days(self, total_days, first_stake_ts):
        start_date = datetime.fromtimestamp(first_stake_ts).strftime('%d.%m.%Y')
        day_count_str = 'days' if total_days >= 2 else 'day'
        return f'{ceil(total_days)} {day_count_str} ({start_date})'

    def text_stake_loading_pools(self, address):
        return f'⏳ <b>Please wait.</b>\n' \
               f'Loading pools information for {pre(address)}...'

    def address_urls(self, address):
        thor_explore_url = get_explorer_url_to_address(self.cfg.network_id, Chains.THOR, address)
        bnb_explore_url = get_explorer_url_to_address(self.cfg.network_id, Chains.BNB, address)
        return thor_explore_url, bnb_explore_url

    def explorer_links_to_thor_address(self, address):
        net = self.cfg.network_id
        if net == NetworkIdents.CHAOSNET_BEP2CHAIN:
            explorer_links = [
                get_explorer_url_to_address(net, Chains.THOR, address),
                get_explorer_url_to_address(net, Chains.BNB, address)
            ]
        else:
            explorer_links = [get_explorer_url_to_address(net, Chains.THOR, address)]

        explorer_links = [link_with_domain_text(url) for url in explorer_links]
        return '; '.join(explorer_links)

    def text_stake_provides_liq_to_pools(self, address, pools):
        pools = pre(', '.join(pools))

        explorer_links = self.explorer_links_to_thor_address(address)

        return f'🛳️ {pre(address)}\nprovides liquidity to the following pools:\n' \
               f'{pools}.\n\n' \
               f"🔍 Explorer: {explorer_links}.\n\n" \
               f'👇 Click on the button to get a detailed card.'

    def text_stake_today(self):
        today = datetime.now().strftime('%d.%m.%Y')
        return f'Today is {today}'

    # ------- CAP -------

    def thor_site(self):
        if self.cfg.network_id == NetworkIdents.CHAOSNET_MULTICHAIN:
            return THOR_SWAP
        else:
            return BEP2_SWAP

    def notification_text_cap_change(self, old: ThorCapInfo, new: ThorCapInfo):
        verb = "has been increased" if old.cap < new.cap else "has been decreased"
        call = "Come on, add more liquidity!\n" if new.cap > old.cap else ''
        message = (
            f'<b>Pool cap {verb} from {pretty_money(old.cap)} to {pretty_money(new.cap)}!</b>\n'
            f'Currently <b>{pretty_money(new.stacked)}</b> {self.R} are in the liquidity pools.\n'
            f"{self._cap_progress_bar(new)}"
            f'The price of {self.R} in the pool is <code>{new.price:.3f} $</code>.\n'
            f'{call}'
            f'{self.thor_site()}'
        )
        return message

    # ------ PRICE -------

    PRICE_GRAPH_TITLE = f'Rune price, USD'
    PRICE_GRAPH_LEGEND_DET_PRICE = f'Deterministic {RAIDO_GLYPH} price'
    PRICE_GRAPH_LEGEND_ACTUAL_PRICE = f'Market {RAIDO_GLYPH} price'

    def price_message(self, info: ThorCapInfo, fair_price: RuneFairPrice):
        return (
            f"Last real price of {self.R} is <code>${info.price:.3f}</code>.\n"
            f"Deterministic price of {self.R} is <code>${fair_price.fair_price:.3f}</code>."
        )

    # ------- NOTIFY STAKES -------

    def links_to_explorer_for_stake_tx(self, tx: LPAddWithdrawTx):
        net = self.cfg.network_id
        if tx.address_rune:
            rune_link = link(
                get_explorer_url_to_address(net, Chains.THOR, tx.address_rune), short_address(tx.address_rune))
        elif tx.tx_hash_rune:
            rune_link = link(
                get_explorer_url_to_tx(net, Chains.THOR, tx.tx_hash_rune), short_address(tx.tx_hash_rune))
        else:
            rune_link = ''

        if tx.address_rune:
            asset_link = link(
                get_explorer_url_to_address(net, tx.pool, tx.address_asset), short_address(tx.address_asset))
        elif tx.tx_hash_rune:
            asset_link = link(
                get_explorer_url_to_tx(net, tx.pool, tx.tx_hash_asset), short_address(tx.tx_hash_asset))
        else:
            asset_link = ''

        return rune_link, asset_link

    def link_to_explorer_user_address_for_stake_tx(self, tx: LPAddWithdrawTx):
        if tx.address_rune:
            return link(
                get_explorer_url_to_address(self.cfg.network_id, Chains.THOR, tx.address_rune),
                short_address(tx.address_rune)
            )
        else:
            return link(
                get_explorer_url_to_address(self.cfg.network_id, tx.pool, tx.address_asset),
                short_address(tx.address_asset)
            )

    def notification_text_large_tx(self, tx: LPAddWithdrawTx, dollar_per_rune: float, pool: StakePoolStats,
                                   pool_info: PoolInfo):
        msg = ''
        if tx.type == ThorTxType.TYPE_ADD_LIQUIDITY:
            msg += f'🐳 <b>Whale added liquidity</b> 🟢\n'
        elif tx.type == ThorTxType.TYPE_WITHDRAW:
            msg += f'🐳 <b>Whale removed liquidity</b> 🔴\n'

        total_usd_volume = tx.full_rune * dollar_per_rune if dollar_per_rune != 0 else 0.0
        pool_depth_usd = pool_info.usd_depth(dollar_per_rune)

        rp, ap = tx.symmetry_rune_vs_asset()

        rune_side_usd = tx.rune_amount * dollar_per_rune
        rune_side_usd_short = short_money(rune_side_usd)
        asset_side_usd_short = short_money(total_usd_volume - rune_side_usd)
        percent_of_pool = pool_info.percent_share(tx.full_rune)

        thor_url, asset_url = self.links_to_explorer_for_stake_tx(tx)
        user_url = self.link_to_explorer_user_address_for_stake_tx(tx)
        chain = chain_name_from_pool(tx.pool)

        msg += (
            f"<b>{pretty_money(tx.rune_amount)} {self.R}</b> ({rp:.0f}% = {rune_side_usd_short}) ↔️ "
            f"<b>{pretty_money(tx.asset_amount)} {short_asset_name(tx.pool)}</b> ({ap:.0f}% = {asset_side_usd_short})\n"
            f"Total: <code>${pretty_money(total_usd_volume)}</code> ({percent_of_pool:.2f}% of the whole pool).\n"
            f"Pool depth is <b>${pretty_money(pool_depth_usd)}</b> now.\n"
            f"User: {user_url}.\n"
            f"Txs: {self.R} – {thor_url} / {chain} – {asset_url}."
        )

        return msg

    # ------- QUEUE -------

    def notification_text_queue_update(self, item_type, step, value):
        if step == 0:
            return f"☺️ Queue {code(item_type)} is empty again!"
        else:
            return (
                f"🤬 <b>Attention!</b> Queue {code(item_type)} has {value} transactions!\n"
                f"{code(item_type)} transactions may be delayed."
            )

    # ------- PRICE -------

    DET_PRICE_HELP_PAGE = 'https://thorchain.org/rune#what-influences-it'

    def notification_text_price_update(self, p: PriceReport, ath=False):
        title = bold('Price update') if not ath else bold('🚀 A new all-time high has been achieved!')

        c_gecko_url = 'https://www.coingecko.com/en/coins/thorchain'
        c_gecko_link = link(c_gecko_url, 'RUNE')

        message = f"{title} | {c_gecko_link}\n\n"
        price = p.fair_price.real_rune_price

        pr_text = f"${price:.3f}"
        btc_price = f"₿ {p.btc_real_rune_price:.8f}"
        message += f"<b>RUNE</b> price is {code(pr_text)} ({btc_price}) now.\n"

        last_ath = p.last_ath
        if last_ath is not None and ath:
            last_ath_pr = f'{last_ath.ath_price:.2f}'
            message += f"Last ATH was ${pre(last_ath_pr)} ({format_time_ago(last_ath.ath_date)}).\n"

        time_combos = zip(
            ('1h', '24h', '7d'),
            (p.price_1h, p.price_24h, p.price_7d)
        )
        for title, old_price in time_combos:
            if old_price:
                pc = calc_percent_change(old_price, price)
                message += pre(f"{title.rjust(4)}:{adaptive_round_to_str(pc, True).rjust(8)} % "
                               f"{emoji_for_percent_change(pc).ljust(4).rjust(6)}") + "\n"

        fp = p.fair_price
        if fp.rank >= 1:
            message += f"Coin market cap is {bold(pretty_dollar(fp.market_cap))} (#{bold(fp.rank)})\n"

        if fp.tlv_usd >= 1:
            det_link = link(self.DET_PRICE_HELP_PAGE, 'deterministic price')
            message += (f"TLV of non-RUNE assets: ${pre(pretty_money(fp.tlv_usd))}\n"
                        f"So {det_link} of RUNE is {code(pretty_money(fp.fair_price, prefix='$'))}\n"
                        f"Speculative multiplier is {pre(x_ses(fp.fair_price, price))}\n")

        return message.rstrip()

    # ------- POOL CHURN -------

    def pool_link(self, pool_name):
        if self.cfg.network_id == NetworkIdents.CHAOSNET_MULTICHAIN:
            return f'https://app.thorswap.finance/pool/{pool_name}'
        else:
            return f'https://chaosnet.bepswap.com/pool/{asset_name_cut_chain(pool_name)}'

    def notification_text_pool_churn(self, added_pools, removed_pools, changed_status_pools):
        message = bold('🏊 Liquidity pool churn!') + '\n\n'

        def pool_text(pool_name, status, to_status=None):
            t = link(self.pool_link(pool_name), pool_name)
            extra = '' if to_status is None else f' → {ital(to_status)}'
            return f'  • {t} ({ital(status)}{extra})'

        if added_pools:
            message += '✅ Pools added:\n' + '\n'.join([pool_text(*a) for a in added_pools]) + '\n\n'
        if removed_pools:
            message += '❌ Pools removed:\n' + '\n'.join([pool_text(*a) for a in removed_pools]) + '\n\n'
        if changed_status_pools:
            message += '🔄 Pools changed:\n' + '\n'.join([pool_text(*a) for a in changed_status_pools]) + '\n\n'

        return message.rstrip()

    # -------- SETTINGS --------

    BUTTON_SET_LANGUAGE = '🌐 Language'
    TEXT_SETTING_INTRO = '<b>Settings</b>\nWhat would you like to tune?'

    # -------- METRICS ----------

    BUTTON_METR_CAP = '📊 Liquidity cap'
    BUTTON_METR_PRICE = f'💲 {R} price info'
    BUTTON_METR_QUEUE = f'👥 Queue'

    TEXT_METRICS_INTRO = 'What metrics would you like to know?'

    TEXT_QUEUE_PLOT_TITLE = 'THORChain Queue'

    def cap_message(self, info: ThorCapInfo):
        return (
            f"Hello! <b>{pretty_money(info.stacked)} {self.R}</b> of "
            f"<b>{pretty_money(info.cap)} {self.R}</b> pooled.\n"
            f"{self._cap_progress_bar(info)}"
            f"The {bold(self.R)} price is <code>${info.price:.3f}</code> now.\n"
        )

    def queue_message(self, queue_info: QueueInfo):
        return (
                   f"<b>Queue info:</b>\n"
                   f"- <b>Outbound</b>: {code(queue_info.outbound)} txs {self.queue_to_smile(queue_info.outbound)}\n"
                   f"- <b>Swap</b>: {code(queue_info.swap)} txs {self.queue_to_smile(queue_info.swap)}\n"
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
        elif n <= 100:
            return '🤬!!'

    TEXT_PRICE_INFO_ASK_DURATION = 'For what period of time do you want to get a graph?'

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
        if network_security_ratio > 0.9:
            return "🥱 INEFFICIENT"
        elif 0.9 >= network_security_ratio > 0.75:
            return "🥸 OVERBONDED"
        elif 0.75 >= network_security_ratio >= 0.6:
            return "⚡ OPTIMAL"
        elif 0.6 > network_security_ratio >= 0.5:
            return "🤢 UNDBERBONDED"
        else:
            return "🤬 INSECURE"

    def notification_text_network_summary(self, old: NetworkStats, new: NetworkStats):
        message = bold('🌐 THORChain stats') + '\n'

        message += '\n'

        security_pb = progressbar(new.network_security_ratio, 1.0, 10)
        security_text = self.network_bond_security_text(new.network_security_ratio)
        message += f'🕸️ Network is {bold(security_text)} {security_pb}.\n'

        active_nodes_change = bracketify(up_down_arrow(old.active_nodes, new.active_nodes, int_delta=True))
        standby_nodes_change = bracketify(up_down_arrow(old.active_nodes, new.active_nodes, int_delta=True))
        message += f"🖥️ {bold(new.active_nodes)} active nodes{active_nodes_change} " \
                   f"and {bold(new.standby_nodes)} standby nodes{standby_nodes_change}.\n"

        current_bond_text = bold(pretty_money(new.total_bond_rune, postfix=RAIDO_GLYPH))
        current_pooled_text = bold(pretty_money(new.total_rune_pooled, postfix=RAIDO_GLYPH))
        current_bond_change = bracketify(up_down_arrow(old.total_bond_rune, new.total_bond_rune, money_delta=True))
        current_pooled_change = bracketify(up_down_arrow(old.total_rune_pooled, new.total_rune_pooled, money_delta=True))

        current_bond_usd_text = bold(pretty_dollar(new.total_bond_usd))
        current_pooled_usd_text = bold(pretty_dollar(new.total_pooled_usd))
        current_bond_usd_change = bracketify(up_down_arrow(old.total_bond_usd, new.total_bond_usd, money_delta=True))
        current_pooled_usd_change = bracketify(
            up_down_arrow(old.total_pooled_usd, new.total_pooled_usd, money_delta=True))

        message += f"🔗 Total bonded: {current_bond_text}{current_bond_change} or " \
                   f"{current_bond_usd_text}{current_bond_usd_change}.\n"
        message += f"🏊 Total pooled: {current_pooled_text}{current_pooled_change} or " \
                   f"{current_pooled_usd_text}{current_pooled_usd_change}.\n"

        reserve_change = bracketify(up_down_arrow(old.reserve_rune, new.reserve_rune,
                                                  postfix=RAIDO_GLYPH, money_delta=True))
        message += f'💰 Reserve: {bold(pretty_money(new.reserve_rune, postfix=RAIDO_GLYPH))}{reserve_change}.\n'

        tlv_change = bracketify(up_down_arrow(old.tlv_usd, new.tlv_usd, money_delta=True, money_prefix='$'))
        message += f'🏦 TLV: {code(pretty_dollar(new.tlv_usd))}{tlv_change}.\n'

        message += '\n'

        if old.is_ok:
            # 24 h Add/withdrawal
            added_24h_rune = new.added_rune - old.added_rune
            withdrawn_24h_rune = new.withdrawn_rune - old.withdrawn_rune
            swap_volume_24h_rune = new.swap_volume_rune - old.swap_volume_rune
            switched_24h_rune = new.switched_rune - old.switched_rune

            add_rune_text = bold(pretty_money(added_24h_rune, prefix=RAIDO_GLYPH))
            withdraw_rune_text = bold(pretty_money(withdrawn_24h_rune, prefix=RAIDO_GLYPH))
            swap_rune_text = bold(pretty_money(swap_volume_24h_rune, prefix=RAIDO_GLYPH))
            switch_rune_text = bold(pretty_money(switched_24h_rune, prefix=RAIDO_GLYPH))

            price = new.usd_per_rune

            add_usd_text = pretty_dollar(added_24h_rune * price)
            withdraw_usd_text = pretty_dollar(withdrawn_24h_rune * price)
            swap_usd_text = pretty_dollar(swap_volume_24h_rune * price)
            switch_usd_text = pretty_dollar(switched_24h_rune * price)

            message += f'{ital("Last 24 hours:")}\n'

            if added_24h_rune:
                message += f'➕ Rune added to pools: {add_rune_text} ({add_usd_text}).\n'
            if withdrawn_24h_rune:
                message += f'➖ Rune withdrawn: {withdraw_rune_text} ({withdraw_usd_text}).\n'
            if swap_volume_24h_rune:
                message += f'🔀 Rune swap volume: {swap_rune_text} ({swap_usd_text}) ' \
                           f'by {bold(new.swaps_24h)} operations.\n'
            if switched_24h_rune:
                message += f'💎 Rune switched to native: {switch_rune_text} ({switch_usd_text}).\n'
            message += '\n'

        if abs(old.bonding_apy - new.bonding_apy) > 0.01:
            bonding_apy_change = bracketify(
                up_down_arrow(old.bonding_apy, new.bonding_apy, money_delta=True, postfix='%'))
        else:
            bonding_apy_change = ''

        if abs(old.liquidity_apy - new.liquidity_apy) > 0.01:
            liquidity_apy_change = bracketify(
                up_down_arrow(old.liquidity_apy, new.liquidity_apy, money_delta=True, postfix='%'))
        else:
            liquidity_apy_change = ''

        message += f'📈 Bonding APY is {code(pretty_money(new.bonding_apy, postfix="%"))}{bonding_apy_change} and ' \
                   f'Liquidity APY is {code(pretty_money(new.liquidity_apy, postfix="%"))}{liquidity_apy_change}.\n'

        message += f'🛡️ Loss protection paid: {code(pretty_dollar(new.loss_protection_paid_usd))}.\n'

        daily_users_change = bracketify(up_down_arrow(old.users_daily, new.users_daily, int_delta=True))
        monthly_users_change = bracketify(up_down_arrow(old.users_monthly, new.users_monthly, int_delta=True))
        message += f'👥 Daily users: {code(new.users_daily)}{daily_users_change}, ' \
                   f'monthly users: {code(new.users_monthly)}{monthly_users_change}\n'

        message += '\n'

        active_pool_changes = bracketify(up_down_arrow(old.active_pool_count,
                                                       new.active_pool_count, int_delta=True))
        pending_pool_changes = bracketify(up_down_arrow(old.pending_pool_count,
                                                         new.pending_pool_count, int_delta=True))
        message += f'{bold(new.active_pool_count)} active pools{active_pool_changes} and ' \
                   f'{bold(new.pending_pool_count)} pending pools{pending_pool_changes}.\n'

        next_pool_wait = seconds_human(new.next_pool_activation_ts - now_ts())
        next_pool = link(self.pool_link(new.next_pool_to_activate), new.next_pool_to_activate)
        message += f"Next pool is likely be activated: {next_pool} in {next_pool_wait}."

        return message
