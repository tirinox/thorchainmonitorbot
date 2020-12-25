from datetime import datetime
from math import ceil

from localization.base import BaseLocalization, RAIDO_GLYPH, CREATOR_TG
from services.lib.datetime import format_time_ago
from services.lib.money import pretty_dollar, pretty_money, short_address, adaptive_round_to_str, calc_percent_change, \
    emoji_for_percent_change, short_asset_name
from services.lib.texts import bold, link, code, ital, pre, x_ses, kbd
from services.models.cap_info import ThorInfo
from services.models.pool_info import PoolInfo
from services.models.price import RuneFairPrice, PriceReport
from services.models.queue import QueueInfo
from services.models.tx import StakeTx, StakePoolStats


class RussianLocalization(BaseLocalization):
    # ---- WELCOME ----
    def help_message(self):
        return (
            f"Этот бот уведомляет о крупных движениях с сети {link(self.THORCHAIN_LINK, 'THORChain')}.\n"
            f"Команды:\n"
            f"/help – эта помощь\n"
            f"/start – запуск и перезапуск бота\n"
            f"/lang – изменить язык\n"
            f"/cap – текущий кап для стейка в пулах Chaosnet\n"
            f"/price – текущая цена {self.R}.\n"
            f"<b>⚠️ Бот теперь уведомляет только в канале @thorchain_alert!</b>\n"
            f"🤗 Отзывы и поддержка: {CREATOR_TG}."
        )

    def welcome_message(self, info: ThorInfo):
        return (
            f"Привет! Здесь ты можешь найти метрики THORChain и узнать результаты предоставления ликвидности в пулы.\n"
            f"Цена {self.R} сейчас <code>{info.price:.3f} BUSD</code>.\n"
            f"<b>⚠️ Бот теперь уведомляет только в канале @thorchain_alert!</b>\n"
            f"Набери /help, чтобы видеть список команд.\n"
            f"🤗 Отзывы и поддержка: {CREATOR_TG}."
        )

    def unknown_command(self):
        return (
            "🙄 Извини, я не знаю такой команды.\n"
            "Нажми на /help, чтобы увидеть доступные команды."
        )

    # ----- MAIN MENU ------

    BUTTON_MM_MY_ADDRESS = '🏦 Мои адреса'
    BUTTON_MM_METRICS = '📐 Метрики'
    BUTTON_MM_SETTINGS = f'⚙️ Настройки'

    def kbd_main_menu(self):
        return kbd([[self.BUTTON_MM_MY_ADDRESS, self.BUTTON_MM_METRICS, self.BUTTON_MM_SETTINGS]])

    # ------ STAKE INFO -----

    BUTTON_SM_ADD_ADDRESS = '➕ Добавить новый адрес'
    BUTTON_BACK = '🔙 Назад'
    BUTTON_SM_BACK_TO_LIST = '🔙 Назад к адресам'
    BUTTON_SM_BACK_MM = '🔙 Главное меню'

    BUTTON_VIEW_RUNESTAKEINFO = '🌎 Открыть на runestake.info'
    BUTTON_VIEW_VALUE_ON = 'Скрыть деньги: НЕТ'
    BUTTON_VIEW_VALUE_OFF = 'Скрыть деньги: ДА'
    BUTTON_REMOVE_THIS_ADDRESS = '❌ Удалить этот адресс'

    TEXT_NO_ADDRESSES = "🔆 Вы еще не добавили никаких адресов. Пришлите мне адрес, чтобы добавить."
    TEXT_YOUR_ADDRESSES = '🔆 Вы добавили следующие адреса:'
    TEXT_INVALID_ADDRESS = code('⛔️ Ошибка в формате адреса!')
    TEXT_SELECT_ADDRESS_ABOVE = 'Выбери адрес выше ☝️ '
    TEXT_SELECT_ADDRESS_SEND_ME = 'Если хотите добавить адрес, пришлите его мне 👇'
    TEXT_LP_NO_POOLS_FOR_THIS_ADDRESS = '📪 <b>На этом адресе нет пулов ликвидности.</b> ' \
                                        'Выберите другой адрес или добавьте новый.'
    TEXT_LP_IMG_CAPTION = f'Сгенерировано: {link(BaseLocalization.START_ME, "@thorchain_monitoring_bot")}'

    LP_PIC_POOL = 'ПУЛ'
    LP_PIC_RUNE = 'RUNE'
    LP_PIC_ADDED = 'Добавлено'
    LP_PIC_WITHDRAWN = 'Выведено'
    LP_PIC_REDEEM = 'Можно забрать'
    LP_PIC_GAIN_LOSS = 'Доход / убыток'
    LP_PIC_IN_USD = 'в USD'
    LP_PIC_R_RUNE = f'{RAIDO_GLYPH}une'
    LP_PIC_ADDED_VALUE = 'Добавлено всего'
    LP_PIC_WITHDRAWN_VALUE = 'Выведено всего'
    LP_PIC_CURRENT_VALUE = 'Осталось в пуле'
    LP_PIC_PRICE_CHANGE = 'Изменение цены'
    LP_PIC_PRICE_CHANGE_2 = 'с момента 1го стейка'
    LP_PIC_LP_VS_HOLD = 'Против ХОЛД'
    LP_PIC_LP_APY = 'Годовых'
    LP_PIC_EARLY = 'Еще рано...'
    LP_PIC_FOOTER = "Испольует runestake.info от Bigboss"

    def pic_stake_days(self, total_days, first_stake_ts):
        start_date = datetime.fromtimestamp(first_stake_ts).strftime('%d.%m.%Y')
        return f'{ceil(total_days)} дн. ({start_date})'

    def text_stake_loading_pools(self, address):
        return f'⏳ <b>Пожалуйста, подождите.</b>\n' \
               f'Идет загрузка пулов для адреса {pre(address)}...\n' \
               f'Иногда она может идти долго, если Midgard сильно нагружен.'

    def text_stake_provides_liq_to_pools(self, address, pools):
        pools = pre(', '.join(pools))
        thor_tx = link(self.thor_explore_address(address), 'viewblock.io')
        bnb_tx = link(self.binance_explore_address(address), 'explorer.binance.org')
        return f'🛳️ {pre(address)}\n' \
               f'поставляет ликвидность в следующие пулы:\n{pools}.\n\n' \
               f"🔍 Explorers: {thor_tx}; {bnb_tx}.\n\n" \
               f'👇 Выберите пул, чтобы получить подробную карточку информаци.'

    def text_stake_today(self):
        today = datetime.now().strftime('%d.%m.%Y')
        return f'Сегодня: {today}'

    # ----- CAP ------
    def notification_text_cap_change(self, old: ThorInfo, new: ThorInfo):
        verb = "подрос" if old.cap < new.cap else "упал"
        call = "Ай-да застейкаем!\n" if new.cap > old.cap else ''
        return (
            f'<b>Кап {verb} с {pretty_money(old.cap)} до {pretty_money(new.cap)}!</b>\n'
            f'Сейчас в пулы помещено <b>{pretty_money(new.stacked)}</b> {self.R}.\n'
            f"{self._cap_progress_bar(new)}"
            f'Цена {self.R} в пуле <code>{new.price:.3f} BUSD</code>.\n'
            f'{call}'
            f'https://chaosnet.bepswap.com/'
        )

    # ------ PRICE -------
    def price_message(self, info: ThorInfo, fair_price: RuneFairPrice):
        return (
            f"Последняя цена {self.R}: <code>{info.price:.3f} BUSD</code>.\n"
            f"Детерминистическая цена {self.R} сейчас: <code>${fair_price.fair_price:.3f}</code>."
        )

    # ------ TXS -------
    def notification_text_large_tx(self, tx: StakeTx, dollar_per_rune: float, pool: StakePoolStats,
                                   pool_info: PoolInfo):
        msg = ''
        if tx.type == 'stake':
            msg += f'🐳 <b>Кит добавил ликвидности</b> 🟢\n'
        elif tx.type == 'unstake':
            msg += f'🐳 <b>Кит вывел ликвидность</b> 🔴\n'

        rp, ap = tx.symmetry_rune_vs_asset()
        total_usd_volume = tx.full_rune * dollar_per_rune if dollar_per_rune != 0 else 0.0
        pool_depth_usd = pool_info.usd_depth(dollar_per_rune)
        thor_tx = link(self.thor_explore_address(tx.address), short_address(tx.address))
        bnb_tx = link(self.binance_explore_address(tx.address), short_address(tx.address))
        percent_of_pool = pool_info.percent_share(tx.full_rune)

        return (
            f"<b>{pretty_money(tx.rune_amount)} {self.R}</b> ({rp:.0f}%) ↔️ "
            f"<b>{pretty_money(tx.asset_amount)} {short_asset_name(tx.pool)}</b> ({ap:.0f}%)\n"
            f"Всего: <code>${pretty_money(total_usd_volume)}</code> ({percent_of_pool:.2f}% от всего пула).\n"
            f"Глубина пула сейчас: <b>${pretty_money(pool_depth_usd)}</b>.\n"
            f"Thor обозреватель: {thor_tx} / Binance обозреватель: {bnb_tx}."
        )

    # ------- QUEUE -------

    def notification_text_queue_update(self, item_type, step, value, include_pic=False):
        if step == 0:
            return f"☺️ Очередь {item_type} снова опустела!"
        else:
            return f"🤬 <b>Внимание!</b> Очередь {code(item_type)} имеет {value} транзакций!"

    # ------- PRICE -------

    def notification_text_price_update(self, p: PriceReport, ath=False):
        title = bold('Обновление цены') if not ath else bold('🚀 Достигнуть новый исторический максимум!')

        c_gecko_url = 'https://www.coingecko.com/ru/' \
                      '%D0%9A%D1%80%D0%B8%D0%BF%D1%82%D0%BE%D0%B2%D0%B0%D0%BB%D1%8E%D1%82%D1%8B/thorchain'
        c_gecko_link = link(c_gecko_url, 'RUNE')

        message = f"{title} | {c_gecko_link}\n\n"
        price = p.fair_price.real_rune_price

        btc_price = f"₿ {p.btc_real_rune_price:.8f}"
        pr_text = f"${price:.2f}"
        message += f"Цена <b>RUNE</b> сейчас {code(pr_text)} ({btc_price}).\n"

        last_ath = p.last_ath
        if last_ath is not None and ath:
            message += f"Последний ATH был ${last_ath.ath_price:2.f} ({format_time_ago(last_ath.ath_date)}).\n"

        time_combos = zip(
            ('1ч.', '24ч.', '7дн.'),
            (p.price_1h, p.price_24h, p.price_7d)
        )
        for title, old_price in time_combos:
            if old_price:
                pc = calc_percent_change(old_price, price)
                message += pre(f"{title.rjust(5)}:{adaptive_round_to_str(pc, True).rjust(8)} % "
                               f"{emoji_for_percent_change(pc).ljust(4).rjust(6)}") + "\n"

        fp = p.fair_price
        if fp.rank >= 1:
            message += f"Капитализация: {bold(pretty_dollar(fp.market_cap))} (#{bold(fp.rank)} место)\n"

        if fp.tlv_usd >= 1:
            message += (f"TLV (кроме RUNE): ${pre(pretty_money(fp.tlv_usd))}\n"
                        f"Детерминистическая цена: {code(pretty_money(fp.fair_price, prefix='$'))}\n"
                        f"Спекулятивый множитель: {pre(x_ses(fp.fair_price, price))}\n")

        return message.rstrip()

    # ------- POOL CHURN -------

    def notification_text_pool_churn(self, added_pools, removed_pools, changed_status_pools):
        message = bold('🏊 Изменения в пулах ликвидности:') + '\n\n'

        statuses = {
            'Enabled': 'включен',
            'Bootstrap': 'загружается'
        }

        def pool_text(pool_name, status, to_status=None):
            t = link(self.pool_link(pool_name), pool_name)
            extra = '' if to_status is None else f' → {ital(statuses[to_status])}'
            return f'{t} ({ital(statuses[status])}{extra})'

        if added_pools:
            message += '✅ Пулы добавлены: ' + ', '.join([pool_text(*a) for a in added_pools]) + '\n'
        if removed_pools:
            message += '❌ Пулы удалены: ' + ', '.join([pool_text(*a) for a in removed_pools]) + '\n'
        if changed_status_pools:
            message += '🔄 Пулы изменились: ' + ', '.join([pool_text(*a) for a in changed_status_pools]) + '\n'

        return message.rstrip()

    # -------- SETTINGS --------

    BUTTON_SET_LANGUAGE = '🌐 Язык'
    TEXT_SETTING_INTRO = '<b>Настройки</b>\nЧто вы хотите поменять в настройках?'

    # -------- METRICS ----------

    BUTTON_METR_CAP = '📊 Кап ливкидности'
    BUTTON_METR_PRICE = f'💲 {BaseLocalization.R} инфо о цене'
    BUTTON_METR_QUEUE = f'👥 Очередь'

    TEXT_METRICS_INTRO = 'Что вы хотите узнать?'

    def cap_message(self, info: ThorInfo):
        return (
            f"<b>{pretty_money(info.stacked)}</b> монет из "
            f"<b>{pretty_money(info.cap)}</b> сейчас застейканы.\n"
            f"{self._cap_progress_bar(info)}"
            f"Цена {bold(self.R)} сейчас <code>{info.price:.3f} BUSD</code>.\n"
        )

    def queue_message(self, queue_info: QueueInfo):
        return (
            f"<b>Информация об очередях:</b>\n"
            f"Исходящие транзакции (outbound): {code(queue_info.outbound)} шт.\n"
            f"Очередь обменов (swap): {code(queue_info.swap)} шт.\n"
        ) + (
            f"Если в очереди много транзакций, ваши операции могут занять гораздо больше времени, чем обычно."
            if queue_info.is_full else ''
        )
