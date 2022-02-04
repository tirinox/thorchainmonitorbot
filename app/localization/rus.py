from datetime import datetime
from math import ceil
from typing import List

from aiothornode.types import ThorChainInfo, ThorBalances
from semver import VersionInfo

from localization.base import BaseLocalization, RAIDO_GLYPH, CREATOR_TG, URL_LEADERBOARD_MCCN
from services.lib.constants import Chains, thor_to_float, rune_origin, BNB_RUNE_SYMBOL
from services.lib.date_utils import format_time_ago, seconds_human, now_ts
from services.lib.explorers import get_explorer_url_to_address, get_explorer_url_to_tx
from services.lib.money import pretty_dollar, pretty_money, short_address, adaptive_round_to_str, calc_percent_change, \
    emoji_for_percent_change, Asset, short_money, short_dollar, format_percent
from services.lib.texts import bold, link, code, ital, pre, x_ses, progressbar, bracketify, \
    up_down_arrow, plural, grouper
from services.models.bep2 import BEP2Transfer, BEP2CEXFlow
from services.models.cap_info import ThorCapInfo
from services.models.last_block import BlockSpeed
from services.models.mimir import MimirChange, MimirHolder
from services.models.net_stats import NetworkStats
from services.models.node_info import NodeSetChanges, NodeInfo, NodeVersionConsensus, NodeEvent, EventDataSlash, \
    NodeEventType, EventBlockHeight
from services.models.pool_info import PoolInfo, PoolChanges, PoolDetailHolder
from services.models.price import PriceReport, RuneMarketInfo
from services.models.queue import QueueInfo
from services.models.tx import ThorTxExtended, ThorTxType


class RussianLocalization(BaseLocalization):
    LOADING = '⌛ Загрузка...'
    SUCCESS = '✅ Успех!'
    ND = 'Неопр.'
    NA = 'Н/Д'

    BOT_LOADING = '⌛ Бот был недавно перезапущен и все еще загружается. Пожалуйста, повторите попытку через пару минут.'

    SHORT_MONEY_LOC = {
        'K': ' тыс',
        'M': ' млн',
        'B': ' млрд',
        'T': ' трлн',
    }

    # ---- WELCOME ----
    def help_message(self):
        return (
            f"Этот бот уведомляет о крупных движениях с сети {link(self.THORCHAIN_LINK, 'THORChain')}.\n"
            f"Команды:\n"
            f"/help – эта помощь\n"
            f"/start – запуск и перезапуск бота\n"
            f"/lang – изменить язык\n"
            f"/cap – текущий кап для ликвидности в пулах Chaosnet\n"
            f"/price – текущая цена {self.R}\n"
            f"/queue – размер очереди транзакций\n"
            f"/nodes – список нод\n"
            f"/stats – THORChain статистика сети\n"
            f"/chains – Подключенные блокчейны\n"
            f"/lp – мониторинг ваших пулов\n"
            f"<b>⚠️ Бот теперь уведомляет только в канале {self.alert_channel_name}!</b>\n"
            f"🤗 Отзывы и поддержка: {CREATOR_TG}."
        )

    def welcome_message(self, info: ThorCapInfo):
        return (
            f"Привет! Здесь ты можешь найти метрики THORChain и узнать результаты предоставления ликвидности в пулы.\n"
            f"Цена {self.R} сейчас <code>{info.price:.3f} $</code>.\n"
            f"<b>⚠️ Бот теперь уведомляет только в канале {self.alert_channel_name}!</b>\n"
            f"Набери /help, чтобы видеть список команд.\n"
            f"🤗 Отзывы и поддержка: {CREATOR_TG}."
        )

    def unknown_command(self):
        return (
            "🙄 Извини, я не знаю такой команды.\n"
            "Нажми на /help, чтобы увидеть доступные команды."
        )

    # ----- MAIN MENU ------

    BUTTON_MM_MY_ADDRESS = '🏦 Мои LP адреса'
    BUTTON_MM_METRICS = '📐 Метрики'
    BUTTON_MM_SETTINGS = f'⚙️ Настройки'
    BUTTON_MM_MAKE_AVATAR = f'🦹‍️️ Сделай аву'
    BUTTON_MM_NODE_OP = '🤖 Операторам нод'

    # ------ LP INFO -----

    BUTTON_SM_ADD_ADDRESS = '➕ Добавить новый адрес'
    BUTTON_BACK = '🔙 Назад'
    BUTTON_SM_BACK_TO_LIST = '🔙 Назад к адресам'
    BUTTON_SM_BACK_MM = '🔙 Главное меню'

    BUTTON_SM_SUMMARY = '💲 Сводка'

    BUTTON_VIEW_RUNE_DOT_YIELD = '🌎 Открыть на runeyield.info'
    BUTTON_VIEW_VALUE_ON = 'Скрыть деньги: НЕТ'
    BUTTON_VIEW_VALUE_OFF = 'Скрыть деньги: ДА'

    BUTTON_LP_PROT_ON = 'IL защита: ДА'
    BUTTON_LP_PROT_OFF = 'IL защита: НЕТ'

    BUTTON_REMOVE_THIS_ADDRESS = '❌ Удалить этот адресс'

    TEXT_NO_ADDRESSES = "🔆 Вы еще не добавили никаких адресов. Пришлите мне адрес, чтобы добавить."
    TEXT_YOUR_ADDRESSES = '🔆 Вы добавили следующие адреса:'
    TEXT_INVALID_ADDRESS = code('⛔️ Ошибка в формате адреса!')
    TEXT_SELECT_ADDRESS_ABOVE = 'Выбери адрес выше ☝️ '
    TEXT_SELECT_ADDRESS_SEND_ME = 'Если хотите добавить адрес, пришлите его мне 👇'
    TEXT_LP_NO_POOLS_FOR_THIS_ADDRESS = '📪 <b>На этом адресе нет пулов ликвидности.</b> ' \
                                        'Выберите другой адрес или добавьте новый.'

    def text_lp_img_caption(self):
        bot_link = "@" + self.this_bot_name
        start_me = self.url_start_me
        return f'Сгенерировано: {link(start_me, bot_link)}'

    LP_PIC_POOL = 'ПУЛ'
    LP_PIC_RUNE = 'RUNE'
    LP_PIC_ADDED = 'Добавлено'
    LP_PIC_WITHDRAWN = 'Выведено'
    LP_PIC_REDEEM = 'Можно забрать'
    LP_PIC_GAIN_LOSS = 'Доход / убыток'
    LP_PIC_IN_USD = 'в USD'
    LP_PIC_IN_USD_CAP = 'или в USD'
    LP_PIC_R_RUNE = f'В {RAIDO_GLYPH}une'
    LP_PIC_IN_ASSET = 'или в {0}'
    LP_PIC_ADDED_VALUE = 'Добавлено всего'
    LP_PIC_WITHDRAWN_VALUE = 'Выведено всего'
    LP_PIC_CURRENT_VALUE = 'В пуле (+чай)'
    LP_PIC_PRICE_CHANGE = 'Изменение цены'
    LP_PIC_PRICE_CHANGE_2 = 'с 1го добавления'
    LP_PIC_LP_VS_HOLD = 'Против ХОЛД'
    LP_PIC_LP_APY = 'Годовых'
    LP_PIC_LP_APY_OVER_LIMIT = 'Очень много %'
    LP_PIC_EARLY = 'Еще рано...'
    LP_PIC_FOOTER = ""  # my LP scanner is used
    LP_PIC_FEES = 'Ваши чаевые'
    LP_PIC_IL_PROTECTION = 'Страховка от IL'
    LP_PIC_NO_NEED_PROTECTION = 'Не требуется'
    LP_PIC_EARLY_TO_PROTECT = 'Рано, подождите...'
    LP_PIC_PROTECTION_DISABLED = 'Отключена'

    LP_PIC_SUMMARY_HEADER = 'Сводка по пулам ликвидности'
    LP_PIC_SUMMARY_ADDED_VALUE = 'Добавлено'
    LP_PIC_SUMMARY_WITHDRAWN_VALUE = 'Выведено'
    LP_PIC_SUMMARY_CURRENT_VALUE = 'Сейчас в пуле'
    LP_PIC_SUMMARY_TOTAL_GAIN_LOSS = 'Доход/убыток'
    LP_PIC_SUMMARY_TOTAL_GAIN_LOSS_PERCENT = 'Доход/убыток %'
    LP_PIC_SUMMARY_AS_IF_IN_RUNE = f'Если все в {RAIDO_GLYPH}'
    LP_PIC_SUMMARY_AS_IF_IN_USD = 'Если все в $'
    LP_PIC_SUMMARY_TOTAL_LP_VS_HOLD = 'Итого холд против пулов, $'
    LP_PIC_SUMMARY_NO_WEEKLY_CHART = "Нет недельного графика, извините..."

    def pic_lping_days(self, total_days, first_add_ts):
        start_date = datetime.fromtimestamp(first_add_ts).strftime('%d.%m.%Y')
        return f'{ceil(total_days)} дн. ({start_date})'

    def text_lp_loading_pools(self, address):
        return f'⏳ <b>Пожалуйста, подождите.</b>\n' \
               f'Идет загрузка пулов для адреса {pre(address)}...\n' \
               f'Иногда она может идти долго, если Midgard сильно нагружен.'

    def text_user_provides_liq_to_pools(self, address, pools, balances: ThorBalances):
        pools = pre(', '.join(pools))
        explorer_links = self.explorer_links_to_thor_address(address)

        balance_str = ''
        if balances is not None:
            bal = balances.runes_float
            balance_str = f'Баланс аккаунта : {pre(short_money(bal, prefix=RAIDO_GLYPH))}.\n\n'

        return f'🛳️ {pre(address)}\n' \
               f'поставляет ликвидность в следующие пулы:\n{pools}.\n\n' \
               f"🔍 Обозреватель: {explorer_links}.\n\n{balance_str}" \
               f'👇 Выберите пул, чтобы получить подробную карточку информаци.'

    def text_lp_today(self):
        today = datetime.now().strftime('%d.%m.%Y')
        return f'Сегодня: {today}'

    # ----- CAP ------

    def notification_text_cap_change(self, old: ThorCapInfo, new: ThorCapInfo):
        up = old.cap < new.cap
        verb = "подрос" if up else "упал"
        arrow = '⬆️' if up else '⚠️ ⬇️'
        call = "Ай-да запулим еще!\n" if up else ''
        return (
            f'{arrow} <b>Кап {verb} с {pretty_money(old.cap)} до {pretty_money(new.cap)}!</b>\n'
            f'Сейчас в пулы помещено <b>{pretty_money(new.pooled_rune)}</b> {self.R}.\n'
            f"{self._cap_progress_bar(new)}\n"
            f'🤲🏻 Вы можете добавить еще {bold(pretty_money(new.how_much_rune_you_can_lp) + " " + RAIDO_GLYPH)} {self.R} '
            f'или {bold(pretty_dollar(new.how_much_usd_you_can_lp))}.\n'
            f'Цена {self.R} в пуле <code>{new.price:.3f} $</code>.\n'
            f'{call}'
            f'{self.thor_site()}'
        )

    def notification_text_cap_full(self, cap: ThorCapInfo):
        return (
            '🙆‍♀️ <b>Ликвидность достигла установленного предела!</b>\n'
            'Пожалуйста, пока что не пытайтесь ничего добавить в пулы. '
            'Вы получите возврат ваших средств!\n'
            f'<b>{pretty_money(cap.pooled_rune)} {self.R}</b> из '
            f"<b>{pretty_money(cap.cap)} {self.R}</b> сейчас в пулах.\n"
            f"{self._cap_progress_bar(cap)}\n"
        )

    def notification_text_cap_opened_up(self, cap: ThorCapInfo):
        return (
            '💡 <b>Освободилось место в пулах ликвидности!</b>\n'
            f'Сейчас в пулах <i>{pretty_money(cap.pooled_rune)} {self.R}</i> из '
            f"<i>{pretty_money(cap.cap)} {self.R}</i> максимально возможных.\n"
            f"{self._cap_progress_bar(cap)}\n"
            f'🤲🏻 Вы можеще еще добавить {bold(pretty_money(cap.how_much_rune_you_can_lp) + " " + RAIDO_GLYPH)} {self.R} '
            f'или {bold(pretty_dollar(cap.how_much_usd_you_can_lp))}.\n👉🏻 {self.thor_site()}'
        )

    # ------ PRICE -------

    PRICE_GRAPH_TITLE = f'Цена {RAIDO_GLYPH}уны'
    PRICE_GRAPH_LEGEND_DET_PRICE = 'Детерминистская цена'
    PRICE_GRAPH_LEGEND_ACTUAL_PRICE = 'Цена пулов'
    PRICE_GRAPH_LEGEND_CEX_PRICE = f'Binance цена'

    # ------ TXS -------

    TEXT_MORE_TXS = ' и {n} еще'

    @staticmethod
    def none_str(x):
        return 'нет' if x is None else x

    def notification_text_large_tx(self, tx: ThorTxExtended,
                                   usd_per_rune: float,
                                   pool_info: PoolInfo,
                                   cap: ThorCapInfo = None):
        (ap, asset_side_usd_short, chain, percent_of_pool, pool_depth_usd, rp, rune_side_usd_short,
         total_usd_volume) = self.lp_tx_calculations(usd_per_rune, pool_info, tx)

        heading = ''
        if tx.type == ThorTxType.TYPE_ADD_LIQUIDITY:
            heading = f'🐳 <b>Кит добавил ликвидности</b> 🟢'
        elif tx.type == ThorTxType.TYPE_WITHDRAW:
            heading = f'🐳 <b>Кит вывел ликвидность</b> 🔴'
        elif tx.type == ThorTxType.TYPE_DONATE:
            heading = f'🙌 <b>Безвозмездное добавление в пул</b>'
        elif tx.type == ThorTxType.TYPE_SWAP:
            heading = f'🐳 <b>Крупный обмен</b> 🔁'
        elif tx.type == ThorTxType.TYPE_REFUND:
            heading = f'🐳️ <b>Большой возврат средств</b> ↩️❗'
        elif tx.type == ThorTxType.TYPE_SWITCH:
            heading = f'🐳 <b>Крупный апгрейд {self.R}</b> 🆙'

        asset = Asset(tx.first_pool).name

        content = ''
        if tx.type in (ThorTxType.TYPE_ADD_LIQUIDITY, ThorTxType.TYPE_WITHDRAW, ThorTxType.TYPE_DONATE):
            if tx.affiliate_fee > 0:
                aff_text = f'Партнерский бонус: {bold(short_dollar(tx.get_affiliate_fee_usd(usd_per_rune)))} ' \
                           f'({format_percent(tx.affiliate_fee)})\n'
            else:
                aff_text = ''
            content = (
                f"<b>{pretty_money(tx.rune_amount)} {self.R}</b> ({rp:.0f}% = {rune_side_usd_short}) ↔️ "
                f"<b>{pretty_money(tx.asset_amount)} {asset}</b> "
                f"({ap:.0f}% = {asset_side_usd_short})\n"
                f"Всего: <code>${pretty_money(total_usd_volume)}</code> ({percent_of_pool:.2f}% от всего пула).\n"
                f"{aff_text}"
                f"Глубина пула сейчас: <b>${pretty_money(pool_depth_usd)}</b>.\n"
            )
        elif tx.type == ThorTxType.TYPE_SWITCH:
            # [Amt] Rune [Blockchain: ERC20/BEP2] -> [Amt] THOR Rune ($usd)
            if tx.first_input_tx and tx.first_output_tx:
                amt = thor_to_float(tx.first_input_tx.first_amount)
                origin = rune_origin(tx.first_input_tx.first_asset)
                content = f"{bold(pretty_money(amt))} {origin} {self.R} ➡️ {bold(pretty_money(amt))} Нативных {self.R}"
        elif tx.type == ThorTxType.TYPE_REFUND:
            inputs = tx.get_asset_summary(in_only=True, short_name=True)
            outputs = tx.get_asset_summary(out_only=True, short_name=True)

            input_str = ', '.join(f"{bold(pretty_money(amount))} {asset}" for asset, amount in inputs.items())
            output_str = ', '.join(f"{bold(pretty_money(amount))} {asset}" for asset, amount in outputs.items())

            content = (
                f"{input_str} ➡️ {output_str} ({pretty_dollar(tx.get_usd_volume(usd_per_rune))})\n"
                f"\nПричина: {pre(tx.meta_refund.reason[:180])}"
            )
        elif tx.type == ThorTxType.TYPE_SWAP:
            content = self.tx_convert_string(tx, usd_per_rune)
            slip_str = f'{tx.meta_swap.trade_slip_percent:.3f} %'
            l_fee_usd = tx.meta_swap.liquidity_fee_rune_float * usd_per_rune

            if tx.affiliate_fee > 0:
                aff_text = f'Партнерский бонус: {bold(short_dollar(tx.get_affiliate_fee_usd(usd_per_rune)))} ' \
                           f'({format_percent(tx.affiliate_fee)})\n'
            else:
                aff_text = ''

            content += (
                f"\n{aff_text}"
                f"Проскальзывание: {bold(slip_str)}\n"
                f"Комиссия пулам: {bold(pretty_dollar(l_fee_usd))}"
            )

        blockchain_components = [f"Пользователь: {self.link_to_explorer_user_address_for_tx(tx)}"]

        if tx.in_tx:
            in_links = self.links_to_txs(tx.in_tx, tx.tx_hash)
            if in_links:
                blockchain_components.append('Входы: ' + in_links)

        if tx.out_tx:
            out_links = self.links_to_txs(tx.out_tx, tx.tx_hash)
            if out_links:
                blockchain_components.append('Выходы: ' + out_links)

        msg = f"{heading}\n{content}\n" + " / ".join(blockchain_components)

        if cap:
            msg += (
                f"\n\n"
                f"Кап ликвидности {self._cap_progress_bar(cap)}.\n"
                f'Вы можете добавить еще {code(pretty_money(cap.how_much_rune_you_can_lp))} {bold(self.R)} '
                f'({pretty_dollar(cap.how_much_usd_you_can_lp)}).'
            )

        return msg.strip()

    # ------- QUEUE -------

    def notification_text_queue_update(self, item_type, step, value):
        if step == 0:
            return f"☺️ Очередь {item_type} снова опустела!"
        else:
            return f"🤬 <b>Внимание!</b> Очередь {code(item_type)} имеет {value} транзакций!"

    # ------- PRICE -------

    def notification_text_price_update(self, p: PriceReport, ath=False, halted_chains=None):
        title = bold('Обновление цены') if not ath else bold('🚀 Достигнуть новый исторический максимум!')

        c_gecko_url = 'https://www.coingecko.com/ru/' \
                      '%D0%9A%D1%80%D0%B8%D0%BF%D1%82%D0%BE%D0%B2%D0%B0%D0%BB%D1%8E%D1%82%D1%8B/thorchain'
        c_gecko_link = link(c_gecko_url, 'RUNE')

        message = f"{title} | {c_gecko_link}\n\n"

        if halted_chains:
            hc = pre(', '.join(halted_chains))
            message += f"🚨 <code>Торговля по-прежнему остановлена на {hc}.</code>\n\n"

        price = p.market_info.pool_rune_price

        btc_price = f"₿ {p.btc_pool_rune_price:.8f}"
        pr_text = f"${price:.2f}"
        message += f"Цена <b>RUNE</b> сейчас {code(pr_text)} ({btc_price}).\n"

        fp = p.market_info

        if fp.cex_price > 0.0:
            message += f"Цена <b>RUNE</b> на централизованной бирже Binance: {bold(pretty_dollar(fp.cex_price))}.\n"

            div = abs(fp.cex_price - price)
            div_p = 100.0 * abs(1.0 - fp.cex_price / price) if price != 0 else 0.0
            message += f"<b>Расхождение</b> родной и BEP2 Руны: {code(pretty_dollar(div))} ({div_p:.1f}%).\n"

        last_ath = p.last_ath
        if last_ath is not None and ath:
            if isinstance(last_ath.ath_date, float):
                last_ath_pr = f'{last_ath.ath_price:.2f}'
            else:
                last_ath_pr = str(last_ath.ath_price)
            ago_str = self.format_time_ago(now_ts() - last_ath.ath_date)
            message += f"Последний ATH был ${pre(last_ath_pr)} ({ago_str}).\n"

        time_combos = zip(
            ('1ч.', '24ч.', '7дн.'),
            (p.price_1h, p.price_24h, p.price_7d)
        )
        for title, old_price in time_combos:
            if old_price:
                pc = calc_percent_change(old_price, price)
                message += pre(f"{title.rjust(5)}:{adaptive_round_to_str(pc, True).rjust(8)} % "
                               f"{emoji_for_percent_change(pc).ljust(4).rjust(6)}") + "\n"

        if fp.rank >= 1:
            message += f"Капитализация: {bold(pretty_dollar(fp.market_cap))} (#{bold(fp.rank)} место)\n"

        if fp.total_trade_volume_usd > 0:
            message += f"Объем торгов сегодня: {bold(pretty_dollar(fp.total_trade_volume_usd))}.\n"

        message += '\n'

        if fp.tlv_usd >= 1:
            message += (f"TVL (не-RUNE активов): ${bold(pretty_money(fp.tlv_usd))}\n"
                        f"Детерминистическая цена: {code(pretty_money(fp.fair_price, prefix='$'))}\n"
                        f"Спекулятивый множитель: {pre(x_ses(fp.fair_price, price))}\n")

        return message.rstrip()

    # ------- POOL CHURN -------

    def notification_text_pool_churn(self, pc: PoolChanges):
        if pc.pools_changed:
            message = bold('🏊 Изменения в пулах ликвидности:') + '\n\n'
        else:
            message = ''

        ru_stat = {
            PoolInfo.DEPRECATED_ENABLED: 'включен',
            PoolInfo.AVAILABLE: 'включен',
            PoolInfo.SUSPENDED: 'приостановлен',

            PoolInfo.DEPRECATED_BOOTSTRAP: 'ожидает',
            PoolInfo.STAGED: 'ожидает'
        }

        def pool_text(pool_name, status, to_status=None):
            if PoolInfo.is_status_enabled(to_status):
                extra = '🎉 ПУЛ АКТИВИРОВАН. Можете делать обмены!'
            else:
                extra = ital(ru_stat[status])
                if to_status is not None:
                    extra += f' → {ital(ru_stat[to_status])}'
                extra = f'({extra})'
            return f'  • {self.pool_link(pool_name)}: {extra}'

        if pc.pools_added:
            message += '✅ Пулы добавлены:\n' + '\n'.join([pool_text(*a) for a in pc.pools_added]) + '\n'
        if pc.pools_removed:
            message += '❌ Пулы удалены:\n' + '\n'.join([pool_text(*a) for a in pc.pools_removed]) + '\n'
        if pc.pools_changed:
            message += '🔄 Пулы изменились:\n' + '\n'.join([pool_text(*a) for a in pc.pools_changed]) + '\n'

        return message.rstrip()

    # -------- SETTINGS --------

    BUTTON_SET_LANGUAGE = '🌐 Язык'
    TEXT_SETTING_INTRO = '<b>Настройки</b>\nЧто вы хотите поменять в настройках?'
    BUTTON_SET_NODE_OP_GOTO = 'Операторам нод'

    # -------- METRICS ----------

    BUTTON_METR_S_FINANCIAL = '💱 Финансовые'
    BUTTON_METR_S_NET_OP = '🔩 Работа сети'

    BUTTON_METR_CAP = '✋ Кап ливкидности'
    BUTTON_METR_PRICE = f'💲 {BaseLocalization.R} инфо о цене'
    BUTTON_METR_QUEUE = f'👥 Очередь'
    BUTTON_METR_STATS = f'📊 Статистика'
    BUTTON_METR_NODES = '🖥 Ноды (узлы)'
    BUTTON_METR_LEADERBOARD = '🏆 Доска рекордов'
    BUTTON_METR_CHAINS = '⛓️ Блокчейны'
    BUTTON_METR_MIMIR = '🎅 Мимир'
    BUTTON_METR_VOTING = '🏛️ Голосование'
    BUTTON_METR_BLOCK_TIME = '⏱️ Время блоков'
    BUTTON_METR_TOP_POOLS = '🏊 Топ Пулов'
    BUTTON_METR_CEX_FLOW = '🌬 Поток бирж'

    TEXT_METRICS_INTRO = 'Что вы хотите узнать?'

    def cap_message(self, info: ThorCapInfo):
        if info.can_add_liquidity:
            rune_vacant = info.how_much_rune_you_can_lp
            usd_vacant = rune_vacant * info.price
            more_info = f'🤲🏻 Можно добавить еще {bold(pretty_money(rune_vacant) + " " + RAIDO_GLYPH)} {self.R} ' \
                        f'или {bold(pretty_dollar(usd_vacant))}.\n👉🏻 {self.thor_site()}'
        else:
            more_info = '🛑 Вы не можете добавлять ликвидность сейчас. Дождитесь уведомления о поднятии капы!'

        return (
            f"<b>{pretty_money(info.pooled_rune)} {RAIDO_GLYPH} {self.R}</b> монет из "
            f"<b>{pretty_money(info.cap)} {RAIDO_GLYPH} {self.R}</b> сейчас в пулах.\n"
            f"{self._cap_progress_bar(info)}\n"
            f"{more_info}\n"
            f"Цена {bold(self.R)} сейчас <code>{info.price:.3f} $</code>.\n"
        )

    def text_leaderboard_info(self):
        return f"🏆 Доска лушчих трейдеров THORChain:\n" \
               f"\n" \
               f" 👉 {bold(URL_LEADERBOARD_MCCN)} 👈\n"

    def queue_message(self, queue_info: QueueInfo):
        return (
                   f"<b>Информация об очередях:</b>\n"
                   f"Исходящие транзакции (outbound): {code(queue_info.outbound)} шт.\n"
                   f"Очередь обменов (swap): {code(queue_info.swap)} шт.\n"
                   f"Внутренняя очередь (internal): {code(queue_info.internal)} шт.\n"
               ) + (
                   f"Если в очереди много транзакций, ваши операции могут занять гораздо больше времени, чем обычно."
                   if queue_info.is_full else ''
               )

    TEXT_PRICE_INFO_ASK_DURATION = 'За какой период времени вы хотите получить график?'

    BUTTON_1_HOUR = '1 часов'
    BUTTON_24_HOURS = '24 часа'
    BUTTON_1_WEEK = '1 неделя'
    BUTTON_30_DAYS = '30 дней'

    # ------- AVATAR -------

    TEXT_AVA_WELCOME = '🖼️ Скинь мне квадратное фото, и я сделаю для тебя аватар в стиле THORChain ' \
                       'с градиентной рамкой. Можешь отправить мне картинку как документ, ' \
                       'чтобы избежать проблем потерей качества из-за сжатия.'

    TEXT_AVA_ERR_INVALID = '⚠️ Фото неправильного формата!'
    TEXT_AVA_ERR_NO_PIC = '⚠️ Не удалось загрузить твое фото из профиля!'
    TEXT_AVA_READY = '🥳 <b>Твой THORChain аватар готов!</b> ' \
                     'Скачай это фото и установи его в Телеграм и социальных сетях.'

    BUTTON_AVA_FROM_MY_USERPIC = '😀 Из фото профиля'

    # ------- NETWORK SUMMARY -------

    def network_bond_security_text(self, network_security_ratio):
        if network_security_ratio > 0.9:
            return "🥱 НЕЭФФЕКТИВНА"
        elif 0.9 >= network_security_ratio > 0.75:
            return "🥸 ПЕРЕОБЕСПЕЧЕНА"
        elif 0.75 >= network_security_ratio >= 0.6:
            return "⚡ ОПТИМАЛЬНА"
        elif 0.6 > network_security_ratio >= 0.5:
            return "🤢 НЕДООБЕСПЕЧЕНА"
        elif network_security_ratio == 0:
            return '🚧 ДАННЫЕ НЕ ПОЛУЧЕНЫ...'
        else:
            return "🤬 НЕБЕЗОПАСНА"

    def notification_text_network_summary(self, old: NetworkStats, new: NetworkStats, market: RuneMarketInfo):
        message = bold('🌐 THORChain статистика') + '\n'

        message += '\n'

        security_pb = progressbar(new.network_security_ratio, 1.0, 10)
        security_text = self.network_bond_security_text(new.network_security_ratio)
        message += f'🕸️ Сейчас сеть {bold(security_text)} {security_pb}.\n'

        active_nodes_change = bracketify(up_down_arrow(old.active_nodes, new.active_nodes, int_delta=True))
        standby_nodes_change = bracketify(up_down_arrow(old.active_nodes, new.active_nodes, int_delta=True))
        message += f"🖥️ {bold(new.active_nodes)} активных нод{active_nodes_change} " \
                   f"и {bold(new.standby_nodes)} нод в режиме ожидания{standby_nodes_change}.\n"

        # -- BOND

        current_bond_text = bold(pretty_money(new.total_active_bond_rune, postfix=RAIDO_GLYPH))
        current_bond_change = bracketify(
            up_down_arrow(old.total_active_bond_rune, new.total_active_bond_rune, money_delta=True))

        current_bond_usd_text = bold(pretty_dollar(new.total_active_bond_usd))
        current_bond_usd_change = bracketify(
            up_down_arrow(old.total_active_bond_usd, new.total_active_bond_usd, money_delta=True, money_prefix='$')
        )

        current_total_bond_text = bold(pretty_money(new.total_bond_rune, postfix=RAIDO_GLYPH))
        current_total_bond_change = bracketify(
            up_down_arrow(old.total_bond_rune, new.total_bond_rune, money_delta=True))

        current_total_bond_usd_text = bold(pretty_dollar(new.total_bond_usd))
        current_total_bond_usd_change = bracketify(
            up_down_arrow(old.total_bond_usd, new.total_bond_usd, money_delta=True, money_prefix='$')
        )

        message += f"🔗 Бонд активных нод: {current_bond_text}{current_bond_change} или " \
                   f"{current_bond_usd_text}{current_bond_usd_change}.\n"

        message += f"🔗 Бонд всех нод: {current_total_bond_text}{current_total_bond_change} или " \
                   f"{current_total_bond_usd_text}{current_total_bond_usd_change}.\n"

        # -- POOL

        current_pooled_text = bold(pretty_money(new.total_rune_pooled, postfix=RAIDO_GLYPH))
        current_pooled_change = bracketify(
            up_down_arrow(old.total_rune_pooled, new.total_rune_pooled, money_delta=True))

        current_pooled_usd_text = bold(pretty_dollar(new.total_pooled_usd))
        current_pooled_usd_change = bracketify(
            up_down_arrow(old.total_pooled_usd, new.total_pooled_usd, money_delta=True, money_prefix='$'))

        message += f"🏊 Всего в пулах: {current_pooled_text}{current_pooled_change} или " \
                   f"{current_pooled_usd_text}{current_pooled_usd_change}.\n"

        # -- LIQ

        current_liquidity_usd_text = bold(pretty_dollar(new.total_liquidity_usd))
        current_liquidity_usd_change = bracketify(
            up_down_arrow(old.total_liquidity_usd, new.total_liquidity_usd, money_delta=True, money_prefix='$'))

        message += f"🌊 Всего ликвидности (TVL): {current_liquidity_usd_text}{current_liquidity_usd_change}.\n"

        # -- TVL

        tlv_change = bracketify(
            up_down_arrow(old.total_locked_usd, new.total_locked_usd, money_delta=True, money_prefix='$'))
        message += f'🏦 TVL + бонды нод: {code(pretty_dollar(new.total_locked_usd))}{tlv_change}.\n'

        # -- RESERVE

        reserve_change = bracketify(up_down_arrow(old.reserve_rune, new.reserve_rune,
                                                  postfix=RAIDO_GLYPH, money_delta=True))

        message += f'💰 Резервы: {bold(pretty_money(new.reserve_rune, postfix=RAIDO_GLYPH))}{reserve_change}.\n'

        # --- FLOWS:

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

            message += f'{ital("За последние 24 часа:")}\n'

            if added_24h_rune:
                message += f'➕ Добавлено в пулы: {add_rune_text} ({add_usd_text}).\n'
            if withdrawn_24h_rune:
                message += f'➖ Выведено из пулов: {withdraw_rune_text} ({withdraw_usd_text}).\n'
            if swap_volume_24h_rune:
                message += f'🔀 Объем торгов: {swap_rune_text} ({swap_usd_text}) ' \
                           f'при {bold(new.swaps_24h)} обменов совершено.\n'
            if switched_24h_rune:
                message += f'💎 Rune конвертировано в нативные: {switch_rune_text} ({switch_usd_text}).\n'
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

        switch_rune_total_text = bold(pretty_money(new.switched_rune, prefix=RAIDO_GLYPH))
        message += (f'💎 Всего Rune перевели в нативные: {switch_rune_total_text} '
                    f'({format_percent(new.switched_rune, market.total_supply)}).'
                    f'\n\n')

        message += f'📈 Доход от бондов в нодах, годовых: {code(pretty_money(new.bonding_apy, postfix="%"))}{bonding_apy_change} и ' \
                   f'доход от пулов в среднем, годовых: {code(pretty_money(new.liquidity_apy, postfix="%"))}{liquidity_apy_change}.\n'

        message += f'🛡️ Выплачено страховки от IL (непостоянных потерь): {code(pretty_dollar(new.loss_protection_paid_usd))}.\n'

        daily_users_change = bracketify(up_down_arrow(old.users_daily, new.users_daily, int_delta=True))
        monthly_users_change = bracketify(up_down_arrow(old.users_monthly, new.users_monthly, int_delta=True))
        message += f'👥 Пользователей за день: {code(new.users_daily)}{daily_users_change}, ' \
                   f'пользователей за месяц: {code(new.users_monthly)}{monthly_users_change}\n'

        message += '\n'

        active_pool_changes = bracketify(up_down_arrow(old.active_pool_count,
                                                       new.active_pool_count, int_delta=True))
        pending_pool_changes = bracketify(up_down_arrow(old.pending_pool_count,
                                                        new.pending_pool_count, int_delta=True))
        message += f'{bold(new.active_pool_count)} активных пулов{active_pool_changes} и ' \
                   f'{bold(new.pending_pool_count)} ожидающих активации пулов{pending_pool_changes}.\n'

        if new.next_pool_to_activate:
            next_pool_wait = self.seconds_human(new.next_pool_activation_ts - now_ts())
            next_pool = self.pool_link(new.next_pool_to_activate)
            message += f"Вероятно, будет активирован пул: {next_pool} через {next_pool_wait}."
        else:
            message += f"Пока что нет достойного пула для активации."

        return message

    # ------- NETWORK NODES -------

    TEXT_PIC_ACTIVE_NODES = 'Активные'
    TEXT_PIC_STANDBY_NODES = 'Ожидающие'
    TEXT_PIC_ALL_NODES = 'Все ноды'
    TEXT_PIC_NODE_DIVERSITY = 'Распределение нод'
    TEXT_PIC_NODE_DIVERSITY_SUBTITLE = 'по провайдеру инфраструктуры'
    TEXT_PIC_OTHERS = 'Другие'
    TEXT_PIC_UNKNOWN = 'Не известно'

    def _format_node_text(self, node: NodeInfo, add_status=False, extended_info=False):
        node_ip_link = link(f'https://www.infobyip.com/ip-{node.ip_address}.html', node.ip_address)
        thor_explore_url = get_explorer_url_to_address(self.cfg.network_id, Chains.THOR, node.node_address)
        node_thor_link = link(thor_explore_url, short_address(node.node_address))

        node_status = node.status.lower()
        if node_status == node.STANDBY:
            status = 'Ожидание'
        elif node_status == node.ACTIVE:
            status = 'Активна'
        elif node_status == node.DISABLED:
            status = 'Отключена!'
        else:
            status = node.status

        extra = ''
        if extended_info:
            if node.slash_points:
                extra += f", {bold(node.slash_points)} штрафов"
            if node.current_award:
                award_text = bold(pretty_money(node.current_award, postfix=RAIDO_GLYPH))
                extra += f", {award_text} награды"

        status = f', ({pre(status)})' if add_status else ''
        return f'{bold(node_thor_link)} ({node_ip_link}, версия {node.version}) ' \
               f'с {bold(pretty_money(node.bond, postfix=RAIDO_GLYPH))} бонд {status}{extra}'.strip()

    def _node_bond_change_after_churn(self, changes: NodeSetChanges):
        bond_in, bond_out = changes.bond_churn_in, changes.bond_churn_out
        bond_delta = bond_in - bond_out
        return f'Изменение активного бонда: {code(short_money(bond_delta, postfix=RAIDO_GLYPH))}'

    def notification_text_for_node_churn(self, changes: NodeSetChanges):
        message = ''

        if changes.nodes_activated or changes.nodes_deactivated:
            message += bold('♻️ Перемешивание нод') + '\n\n'

        message += self._make_node_list(changes.nodes_added, '🆕 Новые ноды появились:', add_status=True)
        message += self._make_node_list(changes.nodes_activated, '➡️ Ноды активироны:')
        message += self._make_node_list(changes.nodes_deactivated, '⬅️️ Ноды деактивированы:')
        message += self._make_node_list(changes.nodes_removed, '🗑️ Ноды отключились или исчезли:', add_status=True)

        if changes.nodes_activated or changes.nodes_deactivated:
            message += self._node_bond_change_after_churn(changes)

        return message.rstrip()

    def node_list_text(self, nodes: List[NodeInfo], status, items_per_chunk=12):
        add_status = False
        if status == NodeInfo.ACTIVE:
            title = '✅ Активные ноды:'
            nodes = [n for n in nodes if n.is_active]
        elif status == NodeInfo.STANDBY:
            title = '⏱ Ожидающие активации ноды:'
            nodes = [n for n in nodes if n.is_standby]
        else:
            title = '❔ Ноды в других статусах:'
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
        msg = bold('🕖 Прогресс обновления протокола THORChain\n\n')

        progress = ver_con.ratio * 100.0
        pb = progressbar(progress, 100.0, 14)

        msg += f'{pb} {progress:.0f} %\n'
        msg += f"{pre(ver_con.top_version_count)} из {pre(ver_con.total_active_node_count)} нод " \
               f"обновились до версии {pre(ver_con.top_version)}\n\n"

        cur_version_txt = self.node_version(data.current_active_version, data, active=True)
        msg += f"⚡️ Активная версия протокола сейчас – {cur_version_txt}\n" + \
               ital('* Это минимальная версия среди всех активных нод.') + '\n\n'

        return msg

    def notification_text_version_upgrade(self,
                                          data: NodeSetChanges,
                                          new_versions: List[VersionInfo],
                                          old_active_ver: VersionInfo,
                                          new_active_ver: VersionInfo):

        msg = bold('💫 Обовление версии протокола THORChain') + '\n\n'

        def version_and_nodes(v, all=False):
            realm = data.nodes_all if all else data.active_only_nodes
            n_nodes = len(data.find_nodes_with_version(realm, v))
            return f"{code(v)} ({n_nodes} {plural(n_nodes, 'нода', 'нод')})"

        current_active_version = data.current_active_version

        if new_versions:
            new_version_joined = ', '.join(version_and_nodes(v, all=True) for v in new_versions)
            msg += f"🆕 Обнаружена новая версия: {new_version_joined}\n\n"

            msg += f"⚡️ Активная версия протокола сейчас – {version_and_nodes(current_active_version)}\n" + \
                   ital('* Это минимальная версия среди всех активных нод.') + '\n\n'

        if old_active_ver != new_active_ver:
            action = 'улучшилась' if new_active_ver > old_active_ver else 'откатилась'
            emoji = '🆙' if new_active_ver > old_active_ver else '⬇️'
            msg += (
                f"{emoji} {bold('Внимание!')} Активная версия протокола {bold(action)} "
                f"с версии {pre(old_active_ver)} "
                f"до версии {version_and_nodes(new_active_ver)}\n\n"
            )

            cnt = data.version_counter(data.active_only_nodes)
            if len(cnt) == 1:
                msg += f"Все активные ноды имеют версию {code(current_active_version)}\n"
            elif len(cnt) > 1:
                msg += bold(f"Самые популярные версии нод:") + '\n'
                for i, (v, count) in enumerate(cnt.most_common(5), start=1):
                    active_node = ' 👈' if v == current_active_version else ''
                    msg += f"{i}. {version_and_nodes(v)} {active_node}\n"
                msg += f"Максимальная доступная версия – {version_and_nodes(data.max_available_version)}\n"

        return msg

    # --------- CHAIN INFO SUMMARY ------------

    def text_chain_info(self, chain_infos: List[ThorChainInfo]):
        text = '⛓️ ' + bold('THORChain подключен к блокчейнам:') + '\n\n'
        for c in chain_infos:
            address_link = link(get_explorer_url_to_address(self.cfg.network_id, c.chain, c.address), 'СКАН')
            status = '🛑 Остановлен' if c.halted else '🆗 Активен'
            text += f'{bold(c.chain)}:\n' \
                    f'Статус: {status}\n' \
                    f'Входящий адрес: {pre(c.address)} {address_link}\n'

            if c.router:
                router_link = link(get_explorer_url_to_address(self.cfg.network_id, c.chain, c.router), 'СКАН')
                text += f'Роутер: {pre(c.router)} {router_link}\n'

            text += f'Цена газа: {pre(c.gas_rate)}\n\n'

        if not chain_infos:
            text += 'Инфо о блокчейнах еще не загружено...'

        return text.strip()

    # --------- MIMIR INFO ------------

    MIMIR_STANDARD_VALUE = "стандарт:"
    MIMIR_OUTRO = f'\n\n🔹 – {ital("Админ Мимир")}\n' \
                  f'🔸 – {ital("Голосование нод")}\n' \
                  f'▪️ – {ital("Автоматика")}'
    MIMIR_NO_DATA = 'Нет данных'
    MIMIR_BLOCKS = 'блоков'
    MIMIR_DISABLED = 'ВЫКЛЮЧЕНО'
    MIMIR_YES = 'ДА'
    MIMIR_NO = 'НЕТ'
    MIMIR_UNDEFINED = 'Неопределено'
    MIMIR_LAST_CHANGE = 'Последнее изменение'

    def text_mimir_intro(self):
        text = f'🎅 {bold("Глобальные константы и Мимир")}\n'
        cheatsheet_link = link(self.MIMIR_CHEAT_SHEET_URL, 'Описание констант')
        what_is_mimir_link = link(self.MIMIR_DOC_LINK, "Что такое мими?")
        text += f"{what_is_mimir_link} А еще {cheatsheet_link}.\n\n"
        return text

    # --------- TRADING HALTED -----------

    def notification_text_trading_halted_multi(self, chain_infos: List[ThorChainInfo]):
        msg = ''

        halted_chains = ', '.join(c.chain for c in chain_infos if c.halted)
        if halted_chains:
            msg += f'🚨🚨🚨 <b>Внимание!</b> Торговля остановлена на блокчейнах: {code(halted_chains)}! ' \
                   f'Воздержитесь от обменов, пока торговля не будет снова запущена! 🚨🚨🚨\n\n'

        resumed_chains = ', '.join(c.chain for c in chain_infos if not c.halted)
        if resumed_chains:
            msg += f'✅ <b>Внимание!</b> Торговля снова возобновлена на блокчейнах: {code(resumed_chains)}!'

        return msg.strip()

    # ---------- BLOCK HEIGHT -----------

    TEXT_BLOCK_HEIGHT_CHART_TITLE = 'THORChain блоков в минут'
    TEXT_BLOCK_HEIGHT_LEGEND_ACTUAL = 'Фактически блоков в минуту'
    TEXT_BLOCK_HEIGHT_LEGEND_EXPECTED = 'Ожидаемая (10 блоков/мин)'

    def notification_text_block_stuck(self, stuck, time_without_new_block):
        good_time = time_without_new_block is not None and time_without_new_block > 1
        str_t = ital(self.seconds_human(time_without_new_block) if good_time else self.NA)
        if stuck:
            return f'📛 {bold("THORChain высота блоков перестала увеличиваться")}!\n' \
                   f'Новые блоки не генерируются уже {str_t}.'
        else:
            return f"🆗 {bold('THORChain снова генерирует блоки!')}\n" \
                   f"Сбой длился {str_t}"

    @staticmethod
    def get_block_time_state_string(state, state_changed):
        if state == BlockSpeed.StateNormal:
            if state_changed:
                return '👌 Скорость генерации блоков вернулась к нормальной.'
            else:
                return '👌 Скорость генерации блоков в норме.'
        elif state == BlockSpeed.StateTooSlow:
            return '🐌 Блоки производятся слишком медленно.'
        elif state == BlockSpeed.StateTooFast:
            return '🏃 Блоки производятся слишком быстро.'
        else:
            return ''

    def notification_text_block_pace(self, state: str, block_speed: float):
        phrase = self.get_block_time_state_string(state, True)
        block_per_minute = self.format_bps(block_speed)
        return f'<b>Обновление по скорости производства блоков THORChain</b>\n' \
               f'{phrase}\n' \
               f'В настоящий момент <code>{block_per_minute}</code> блоков в минуту.'

    def text_block_time_report(self, last_block, last_block_ts, recent_bps, state):
        phrase = self.get_block_time_state_string(state, False)
        block_per_minute = self.format_bps(recent_bps)
        ago = self.format_time_ago(last_block_ts)
        block_str = f"#{last_block}"
        return f'<b>THORChain темпы производства блоков.</b>\n' \
               f'{phrase}\n' \
               f'В настоящее время <code>{block_per_minute}</code> блоков в минуту.\n' \
               f'Последний номер блока THORChain: {code(block_str)} (обновлено: {ago}).'

    # --------- MIMIR CHANGED -----------

    def notification_text_mimir_changed(self, changes: List[MimirChange], mimir: MimirHolder):
        if not changes:
            return ''

        text = '🔔 <b>Обновление Мимир!</b>\n\n'

        for change in changes:
            old_value_fmt = code(self.format_mimir_value(change.old_value, change.entry))
            new_value_fmt = code(self.format_mimir_value(change.new_value, change.entry))
            name = code(change.entry.pretty_name if change.entry else change.name)

            e = change.entry
            if e:
                if e.source == e.SOURCE_AUTO:
                    text += bold('[🤖 Автоматика платежеспособности ]  ')
                elif e.source == e.SOURCE_ADMIN:
                    text += bold('[👩‍💻 Администраторы ]  ')
                elif e.source == e.SOURCE_NODE:
                    text += bold('[🤝 Голосование нод ]  ')
                elif e.source == e.SOURCE_NODE_CEASED:
                    text += bold('[💔 Мимир нод отменен ]  ')

            if change.kind == MimirChange.ADDED_MIMIR:
                text += (
                    f'➕ Настройка "{name}" теперь переопределена новым Мимиром. '
                    f'Старое значение по умолчанию было: {old_value_fmt} → '
                    f'новое значение стало: {new_value_fmt}‼️'
                )
            elif change.kind == MimirChange.REMOVED_MIMIR:
                text += (
                    f'➖ Настройка Мимира "{name}" была удалена! '
                    f'Она имела значение: {old_value_fmt} → '
                    f'теперь она вернулась к исходной константе: {new_value_fmt}‼️'
                )
            else:
                text += (
                    f'🔄 Настройка Мимира "{name}" была изменена. '
                    f'Старое значение: {old_value_fmt} → '
                    f'новое значение теперь: {new_value_fmt}‼️'
                )
                if change.entry.automatic:
                    text += f' (на блоке #{ital(change.new_value)}).'
            text += '\n\n'

        text += link("https://docs.thorchain.org/how-it-works/governance#mimir", "Что такое Mimir?")

        return text

    # ------- NODE OP TOOLS -------

    BUTTON_NOP_ADD_NODES = '➕ Добавь ноды'
    BUTTON_NOP_MANAGE_NODES = '🖊️ Редактировать'
    BUTTON_NOP_SETTINGS = '⚙️ Настройки'

    def pretty_node_desc(self, node: NodeInfo, name=None):
        addr = self.short_node_name(node.node_address, name)
        return f'{pre(addr)} ({bold(short_money(node.bond, prefix="R"))} бонд)'

    TEXT_NOP_INTRO_HEADING = bold('Добро пожаловать в Инстременты Операторов Нод.')

    def text_node_op_welcome_text_part2(self, watch_list: dict, last_signal_ago: float):
        text = 'Мы будем отправлять вам персонифицированные уведомления ' \
               'когда что-то важное случается с нодами, которые вы мониторите.\n\n'
        if watch_list:
            text += f'У вас {len(watch_list)} нод в списке слежения.'
        else:
            text += f'Вы не добавили еще пока ни одной ноды в список слежения. ' \
                    f'Нажмите "{ital(self.BUTTON_NOP_ADD_NODES)}" сперва 👇.'

        text += f'\n\nПоследний сигнал был: {ital(self.format_time_ago(last_signal_ago))}'
        if last_signal_ago > 60:
            text += '🔴'
        elif last_signal_ago > 20:
            text += '🟠'
        else:
            text += '🟢'

        return text

    TEXT_NOP_MANAGE_LIST_TITLE = \
        'Вы добавили <pre>{n}</pre> нод в ваш список слежения. ' \
        'Вы можете убрать ноды из списка слежения, нажав на кпонки снизу.'

    TEXT_NOP_ADD_INSTRUCTIONS = '🤓 Если вам уже известны адреса интересующих вас нод, ' \
                                f'пожалуйста, отправьте мне их списком через сообщение. ' \
                                f'Вы можете использовать полный адрес {pre("thorAbc5andD1so2on")} или ' \
                                f'последние 3 или более символов. ' \
                                f'Имена нод в списке могут быть разделены пробелами, запятыми или энтерами.\n\n' \
                                f'Пример: {pre("66ew, xqmm, 7nv9")}'
    BUTTON_NOP_ADD_ALL_NODES = 'Добавить все ноды'
    BUTTON_NOP_ADD_ALL_ACTIVE_NODES = 'Добавить все активные'

    TEXT_NOP_SEARCH_NO_VARIANTS = 'Совпадений не найдено! Попробуйте уточнить свой запрос ' \
                                  'или воспользуйтесь списком для поиска нужных нод.'
    TEXT_NOP_SEARCH_VARIANTS = 'Мы нашли следующие ноды, подходящие под ваш поисковый запрос:'

    TEXT_NOP_SETTINGS_TITLE = 'Настройте ваши уведомления здесь. Выберите тему для настройки:'

    BUTTON_NOP_SETT_SLASHING = 'Штрафы'
    BUTTON_NOP_SETT_VERSION = 'Версии'
    BUTTON_NOP_SETT_OFFLINE = 'Оффлайн'
    BUTTON_NOP_SETT_CHURNING = 'Перемешивание'
    BUTTON_NOP_SETT_BOND = 'Бонд'
    BUTTON_NOP_SETT_HEIGHT = 'Высота блоков'
    BUTTON_NOP_SETT_IP_ADDR = 'IP адр.'
    BUTTON_NOP_SETT_PAUSE_ALL = 'Приостановить все уведомления'

    @staticmethod
    def text_enabled_disabled(is_on):
        return 'включены' if is_on else 'выключены'

    def text_nop_slash_enabled(self, is_on):
        en_text = self.text_enabled_disabled(is_on)
        return f'Уведомления о начислении штрафных очков нодам {bold(en_text)}.'

    def text_nop_bond_is_enabled(self, is_on):
        en_text = self.text_enabled_disabled(is_on)
        return f'Уведомления об изменении бонда {bold(en_text)}.'

    def text_nop_new_version_enabled(self, is_on):
        en_text = self.text_enabled_disabled(is_on)
        return f'Уведомления о появлении новой версии {bold(en_text)}.\n\n' \
               f'<i>На следующием шаге вы настроите уведомления об обновлении ваших нод.</i>'

    def text_nop_version_up_enabled(self, is_on):
        en_text = self.text_enabled_disabled(is_on)
        return f'Уведомления об обновлении версии ноды {bold(en_text)}.'

    def text_nop_offline_enabled(self, is_on):
        en_text = self.text_enabled_disabled(is_on)
        return f'Уведомления об уходе ноды в оффлайн и возврате в онлайн {bold(en_text)}.\n\n' \
               f'<i>На следующих шагах вы настроите сервисы.</i>'

    def text_nop_churning_enabled(self, is_on):
        en_text = self.text_enabled_disabled(is_on)
        return f'Уведомлении о перемешивании нод {bold(en_text)}.\n\n' \
               f'<i>Вы получите персональное уведомление, ' \
               f'если ваша нода вступает в активный набор нод или покидает его.</i>'

    def text_nop_ip_address_enabled(self, is_on):
        en_text = self.text_enabled_disabled(is_on)
        return f'Уведомления об смене IP адреса {bold(en_text)}.\n\n' \
               f'<i>Вы получите уведомление, если нода вдруг изменит свой IP адрес.</i>'

    def text_nop_ask_offline_period(self, current):
        return f'Какой лимит времени вы хотите установить для оффлайн уведомлений?\n\n' \
               f'Если с сервисами вашей ноды нет соединения в течении указанного времени, ' \
               f'то вы получите сообщение.\n\n' \
               f'Сейчас: {pre(self.seconds_human(current))}.'

    def text_nop_chain_height_enabled(self, is_on):
        en_text = self.text_enabled_disabled(is_on)
        return f'Уведомления о зависших клиентах блокчейнов {bold(en_text)}.\n\n' \
               f'<i>Вы получите уведомление, если ваши блокчейн клиенты на нодах перестали сканировать блоки.</i>'

    BUTTON_NOP_LEAVE_ON = '✔ Вкл.'
    BUTTON_NOP_LEAVE_OFF = '✔ Выкл.'
    BUTTON_NOP_TURN_ON = 'Вкл.'
    BUTTON_NOP_TURN_OFF = 'Выкл.'

    BUTTON_NOP_INTERVALS = {
        '2m': '2 мин',
        '5m': '5 мин',
        '15m': '15 мин',
        '30m': '30 мин',
        '60m': '1 час',
        '2h': '2 часа',
        '6h': '6 ч.',
        '12h': '12 ч.',
        '24h': '1 день',
        '3d': '3 дня',
    }

    TEXT_NOP_SLASH_THRESHOLD = 'Выберете порог для сообщений о ' \
                               'штрафных очках (рекомендуем в районе 5 - 10):'

    def text_nop_ask_slash_period(self, pts):
        return f'Отлично! Выберите период мониторинга.\n' \
               f'К примеру, если вы установите <i>10 минут</i> и порог <i>{pts} очков</i>, то ' \
               f'вы получите уведомление, если ваша нода наберет ' \
               f'<i>{pts} очков штрафа</i> за последние <i>10 минут</i>.'

    def text_nop_ask_chain_height_lag_time(self, current_lag_time):
        return 'Пожалуйста, выберите промежуток времени для порога уведомления. ' \
               'Если ваша нода не сканирует блоки более этого времени, то вы получите уведомление об этом.\n\n' \
               'Если пороговое время меньше типичного времени блока для какой-либо цепочки блоков, ' \
               'то оно будет увеличено до 150% от типичного времени (15 минут для BTC).'

    def text_nop_success_add_banner(self, node_addresses):
        node_addresses_text = ','.join([self.short_node_name(a) for a in node_addresses])
        node_addresses_text = node_addresses_text[:80]  # just in case!
        message = f'😉 Успех! {node_addresses_text} добавлены в ваш список. ' \
                  f'Ожидайте уведомлений, если произойдет что-то важное!'
        return message

    BUTTON_NOP_CLEAR_LIST = '🗑️ Очистить все ({n})'
    BUTTON_NOP_REMOVE_INACTIVE = '❌ Убрать неактивные ({n})'
    BUTTON_NOP_REMOVE_DISCONNECTED = '❌ Убрать отключенные ({n})'

    def text_nop_success_remove_banner(self, node_addresses):
        node_addresses_text = ','.join([self.short_node_name(a) for a in node_addresses])
        node_addresses_text = node_addresses_text[:120]  # just in case!
        return f'😉 Успех! Вы убрали ноды из вашего списка слежения: ' \
               f'{node_addresses_text} ({len(node_addresses)} всего).'

    def notification_text_for_node_op_changes(self, c: NodeEvent):
        message = ''
        short_addr = self.node_link(c.address)
        if c.type == NodeEventType.SLASHING:
            data: EventDataSlash = c.data
            date_str = self.seconds_human(data.interval_sec)
            message = f'🔪 Нода {short_addr} получила штраф ' \
                      f'на {bold(data.delta_pts)} очков ≈{date_str} ' \
                      f'(сейчас в сумме: <i>{data.current_pts}</i> штрафных очков)!'
        elif c.type == NodeEventType.VERSION_CHANGED:
            old, new = c.data
            message = f'🆙 Нода {short_addr} обновилась с версии {ital(old)} до {bold(new)}!'
        elif c.type == NodeEventType.NEW_VERSION_DETECTED:
            message = f'🆕 Новая версия ПО ноды обнаружена! {bold(c.data)}! Рассмотрите возможность обновиться!'
        elif c.type == NodeEventType.IP_ADDRESS_CHANGED:
            old, new = c.data
            message = f'🏤 Нода {short_addr} сменила свой IP адрес с {ital(old)} на {bold(new)}!'
        elif c.type == NodeEventType.SERVICE_ONLINE:
            online, duration, service = c.data
            service = bold(str(service).upper())
            if online:
                message = f'✅ Сервис {service} ноды {short_addr} опять вернулся в <b>онлайн</b>!'
            else:
                message = f'🔴 Сервис {service} ноды {short_addr} ушел в <b>оффлайн</b> ' \
                          f'(уже как {self.seconds_human(duration)})!'
        elif c.type == NodeEventType.CHURNING:
            verb = 'активировалась ⬅️' if c.data else 'вышла из активного набора ➡️'
            bond = c.node.bond
            message = f'🌐 Нода {short_addr} ({short_money(bond)} {RAIDO_GLYPH} бонда) {bold(verb)}!'
        elif c.type in NodeEventType.BLOCK_HEIGHT:
            data: EventBlockHeight = c.data

            if data.is_sync:
                message = f'✅ Нода {short_addr} догнала актуальные блоки на блокчейне {pre(data.chain)}.'
            else:
                message = f'🔴 Нода {short_addr} на {pre(data.block_lag)} позади ' \
                          f'на блокчейне {pre(data.chain)} (≈{self.seconds_human(data.how_long_behind)})!'

        return message

    # ------- BEST POOLS -------

    def notification_text_best_pools(self, pd: PoolDetailHolder, n_pools):
        no_pool_text = 'Пока ничего, наверное, еще грузится...'
        text = '\n\n'.join([self.format_pool_top(top_pools, pd, title, no_pool_text, n_pools) for title, top_pools in [
            ('💎 Лучшие годовые %', pd.BY_APY),
            ('💸 Большие объемы', pd.BY_VOLUME_24h),
            ('🏊 Максимальная ликвидность', pd.BY_DEPTH),
        ]])

        return text

    # ------------------------------------------

    DATE_TRANSLATOR = {
        'just now': 'прямо сейчас',
        'never': 'никогда',
        'sec': 'сек',
        'min': 'мин',
        'hour': 'час',
        'hours': 'час',
        'day': 'дн',
        'days': 'дн',
        'ago': 'назад',
    }

    def format_time_ago(self, d):
        return format_time_ago(d, translate=self.DATE_TRANSLATOR)

    def seconds_human(self, s):
        return seconds_human(s, translate=self.DATE_TRANSLATOR)

    # ----- BEP 2 ------

    def notification_text_bep2_movement(self, transfer: BEP2Transfer, rune_price: float):
        usd_amt = transfer.amount * rune_price
        from_link, to_link = self.link_to_bep2(transfer.from_addr), self.link_to_bep2(transfer.to_addr)
        pf = ' ' + BNB_RUNE_SYMBOL
        tf_link = get_explorer_url_to_tx(self.cfg.network_id, Chains.BNB, transfer.tx_hash)
        return (f'<b>️{RAIDO_GLYPH} Крупный {link(tf_link, "перевод")} BEP2 Rune:</b>\n'
                f'{pre(short_money(transfer.amount, postfix=pf))} '
                f'({ital(short_dollar(usd_amt, self.SHORT_MONEY_LOC))}) '
                f'от {from_link} ➡️ к {to_link}.')

    def notification_text_cex_flow(self, bep2flow: BEP2CEXFlow, rune_price: float):
        return (f'🌬️ <b>BEP2.Rune потоки с централизованнвых бирж последние сутки</b>\n'
                f'Завели: {pre(short_money(bep2flow.rune_cex_inflow, postfix=RAIDO_GLYPH))} '
                f'({short_dollar(bep2flow.rune_cex_inflow * rune_price)})\n'
                f'Вывели: {pre(short_money(bep2flow.rune_cex_outflow, postfix=RAIDO_GLYPH))} '
                f'({short_dollar(bep2flow.rune_cex_outflow * rune_price)})\n'
                f'Поток: {pre(short_money(bep2flow.rune_cex_netflow, postfix=RAIDO_GLYPH))} '
                f'({short_dollar(bep2flow.rune_cex_netflow * rune_price)})')
