from datetime import datetime
from typing import List, Tuple

from math import ceil

from api.aionode.types import ThorChainInfo, thor_to_float
from api.midgard.name_service import NameMap
from api.w3.dex_analytics import DexReportEntry, DexReport
from jobs.fetch.chain_id import AlertChainIdChange
from lib.config import Config
from lib.constants import Chains, ThorRealms
from lib.date_utils import format_time_ago, seconds_human, now_ts
from lib.explorers import get_explorer_url_to_address, get_ip_info_link, get_thoryield_address
from lib.money import pretty_dollar, pretty_money, short_address, short_money, short_dollar, format_percent, \
    RAIDO_GLYPH, short_rune, pretty_percent, \
    chart_emoji, pretty_rune
from lib.texts import bold, link, code, ital, pre, progressbar, bracketify, \
    up_down_arrow, plural, shorten_text, cut_long_text
from lib.utils import grouper, translate, hit_every
from models.asset import Asset
from models.wasm import WasmPeriodStats
from models.cap_info import ThorCapInfo
from models.circ_supply import EventRuneBurn
from models.key_stats_model import AlertKeyStats
from models.last_block import BlockProduceState, EventBlockSpeed
from models.lp_info import LiquidityPoolReport
from models.memo import ActionType
from models.mimir import MimirChange, MimirHolder
from models.net_stats import AlertNetworkStats
from models.node_info import NodeSetChanges, NodeInfo, NodeEvent, EventDataSlash, \
    NodeEventType, EventBlockHeight, EventProviderStatus, EventProviderBondChange, BondProvider
from models.pool_info import PoolInfo, PoolChanges, EventPools
from models.price import AlertPrice, RuneMarketInfo, AlertPriceDiverge
from models.queue import QueueInfo
from models.ruji import AlertRujiraMergeStats
from models.runepool import AlertPOLState, AlertRunePoolAction, AlertRunepoolStats
from models.s_swap import AlertSwapStart
from models.secured import AlertSecuredAssetSummary
from models.tcy import TcyFullInfo
from models.trade_acc import AlertTradeAccountAction, AlertTradeAccountStats
from models.transfer import NativeTokenTransfer, RuneCEXFlow
from models.tx import EventLargeTransaction
from models.version import AlertVersionUpgradeProgress, AlertVersionChanged
from .achievements.ach_rus import AchievementsRussianLocalization
from .eng_base import BaseLocalization, CREATOR_TG, URL_OUR_REF


class RussianLocalization(BaseLocalization):
    def __init__(self, cfg: Config):
        super().__init__(cfg)
        self.ach = AchievementsRussianLocalization()

    TEXT_REF_CALL = f'Начни 👉 {link(URL_OUR_REF, "торговать сейчас")} ⚡!'

    COIN_GECKO_URL = ("https://www.coingecko.com/ru/"
                      "%D0%9A%D1%80%D0%B8%D0%BF%D1%82%D0%BE%D0%B2%D0%B0%D0%BB%D1%8E%D1%82%D1%8B/thorchain")

    LOADING = '⌛ <i>Загрузка...</i>'
    SUCCESS = '✅ Успех!'
    ND = 'Неопр.'
    NA = 'Н/Д'

    LIST_NEXT_PAGE = 'След. стр. »'
    LIST_PREV_PAGE = '« Пред. стр.'

    BOT_LOADING = '⌛ Бот был недавно перезапущен и все еще загружается. Пожалуйста, повторите попытку через пару минут.'

    RATE_LIMIT_WARNING = '🔥 <b>Внимание!</b>\n' \
                         'Кажется, вы получаете слишком много персональных уведомлений. ' \
                         'На некоторое время получение будет ограничено. ' \
                         'Проверьте настройки, чтобы отрегулировать частоту уведомлений.'

    SHORT_MONEY_LOC = {
        'K': ' тыс',
        'M': ' млн',
        'B': ' млрд',
        'T': ' трлн',
    }

    @staticmethod
    def _announcement():
        return (
            '\n\n'
            '➡️ Русскоязычные группы THORChain переехали: \n'
            ' 👉 <b>https://t.me/ThorchainRus</b> (основная) \n'
            ' 👉 <b>https://t.me/runetradingru2</b> (торговля, флуд)'
        )

    @classmethod
    def _conditional_announcement(cls):
        return cls._announcement() if hit_every('rus_tg_move', 100) else ''

    # ---- WELCOME ----
    def help_message(self):
        return (
            f"Этот бот уведомляет о крупных движениях с сети {link(self.THORCHAIN_LINK, 'THORChain')}.\n"
            f"Команды:\n"
            f"/help – эта помощь\n"
            f"/start – запуск и перезапуск бота\n"
            f"/lang – изменить язык\n"
            f"/lp – мониторинг ваших кошельков и пулов\n"
            f"/price – текущая цена {self.R}\n"
            f"/queue – размер очереди транзакций\n"
            f"/nodes – список нод\n"
            f"/stats – THORChain статистика сети\n"
            f"/chains – Подключенные блокчейны\n"
            f"/pool – лучшие пулы\n"
            f"/mimir – список констант Мимир\n"
            f"/weekly – недельная статистика THORChain\n"
            f"<b>⚠️ Бот теперь уведомляет только в канале {self.alert_channel_name}!</b>\n"
            f"🤗 Отзывы и поддержка: {CREATOR_TG}."
        )

    def welcome_message(self, info: ThorCapInfo):
        return (
            f"Привет! Здесь ты можешь найти метрики THORChain и узнать результаты предоставления ликвидности в пулы.\n"
            f"Цена {self.R} сейчас <code>{info.price:.3f} $</code>.\n"
            f"Набери /help, чтобы видеть список команд.\n"
            f"🤗 Отзывы и поддержка: {CREATOR_TG}.{self._announcement()}"
        )

    def unknown_command(self):
        return (
            "🙄 Извини, я не знаю такой команды.\n"
            "Нажми на /help, чтобы увидеть доступные команды."
        )

    # ----- MAIN MENU ------

    BUTTON_MM_MY_ADDRESS = '🏦 Мои кошельки'
    BUTTON_MM_METRICS = '📐 Метрики'
    BUTTON_MM_SETTINGS = f'⚙️ Настройки'
    BUTTON_MM_MAKE_AVATAR = f'🦹‍️️ Сделай аву'
    BUTTON_MM_NODE_OP = '🤖 Операторам нод'

    # ------ MY WALLETS MENU -----

    BUTTON_SM_ADD_ADDRESS = '➕ Добавить новый адрес'
    BUTTON_BACK = '🔙 Назад'
    BUTTON_SM_BACK_TO_LIST = '🔙 Назад к адресам'
    BUTTON_SM_BACK_MM = '🔙 Главное меню'

    BUTTON_SM_SUMMARY = '💲 Сводка'

    BUTTON_VIEW_RUNE_DOT_YIELD = '🌎 Открыть на THORYield'
    BUTTON_VIEW_VALUE_ON = 'Скрыть деньги: НЕТ'
    BUTTON_VIEW_VALUE_OFF = 'Скрыть деньги: ДА'

    BUTTON_TRACK_BALANCE_ON = 'Следить за балансом: ДА'
    BUTTON_TRACK_BALANCE_OFF = 'Следить за балансом: НЕТ'

    BUTTON_TRACK_BOND_ON = 'Следить за бондом: ДА'
    BUTTON_TRACK_BOND_OFF = 'Следить за бондом: НЕТ'

    BUTTON_SET_RUNE_ALERT_LIMIT = 'Уст. мин. лимит R'

    BUTTON_REMOVE_THIS_ADDRESS = '❌ Удалить этот адрес'

    BUTTON_LP_SUBSCRIBE = '🔔 Подписаться'
    TEXT_SUBSCRIBE_TO_LP = '🔔 Подписаться на автоматические уведомления о данной позиции? ' \
                           'Вы будете получать отчеты о доходности в это же время через день, неделю или месяц.'
    BUTTON_LP_UNSUBSCRIBE = '🔕 Отписаться'
    BUTTON_LP_UNSUBSCRIBE_ALL = '🔕 Отписаться от всех'
    BUTTON_LP_PERIOD_1D = 'Каждый день'
    BUTTON_LP_PERIOD_1W = 'Каждую неделю'
    BUTTON_LP_PERIOD_1M = 'Каждый месяц'
    ALERT_SUBSCRIBED_TO_LP = '🔔 Вы подписались'
    ALERT_UNSUBSCRIBED_FROM_LP = '🔕 Вы отписались'
    ALERT_UNSUBSCRIBE_FAILED = 'Отписка не удалась!'

    @staticmethod
    def text_error_delivering_report(self, e, address, pool):
        return (
            f'🔥 Ошибка при отправке отчета: {e}. '
            f'Вы отписаны от уведомления. '
            f'Попробуйте подписаться позже или обратитесь к разработчику. {CREATOR_TG}\n\n'
            f'Адрес {ital(address)}, пул {ital(pool)}'
        )

    @staticmethod
    def text_subscribed_to_lp(period):
        next_ts = now_ts() + period
        next_date = datetime.fromtimestamp(next_ts).strftime('%d.%m.%Y %H:%M:%S')
        next_date += ' UTC'
        return f'🔔 <b>Поздравляем!</b> Вы подписались на уведомления о доходности по данной позиции.\n' \
               f'Ближайшее обновление поступит вам {ital(next_date)}.'

    TEXT_WALLETS_INTRO = (
        'Здесь вы можете добавить адреса кошельков, за которыми хотите следить. Доступны следующие возможности:\n'
        '👉 Предоставление ликвидности\n'
        '👉 Слежение за балансами и действиями\n'
        '👉 Предоставление бонда в ноды 🆕\n'
        '👉 Заёмы 🆕\n'
    )
    TEXT_NO_ADDRESSES = "🔆 Вы еще не добавили никаких адресов. Пришлите мне адрес, чтобы добавить."
    TEXT_YOUR_ADDRESSES = '🔆 Вы добавили следующие адреса:'
    TEXT_INVALID_ADDRESS = code('⛔️ Ошибка в формате адреса!')
    TEXT_SELECT_ADDRESS_ABOVE = 'Выбери адрес выше ☝️ '
    TEXT_SELECT_ADDRESS_SEND_ME = 'Если хотите добавить адрес, пришлите его мне 👇'
    TEXT_LP_NO_POOLS_FOR_THIS_ADDRESS = '📪 <i>На этом адресе нет пулов ликвидности.</i>'
    TEXT_CANNOT_ADD = '😐 Простите, но вы не можете добавить этот адрес.'
    TEXT_ANY = 'Любые'

    TEXT_INVALID_LIMIT = '⛔ <b>Неправильное число!</b> Вам следует ввести положительное число.'

    BUTTON_CANCEL = 'Отмена'

    BUTTON_WALLET_SETTINGS = '⚙️ Настройки кошелька'
    BUTTON_WALLET_NAME = 'Задать имя'
    BUTTON_CLEAR_NAME = 'Отвязать имя'

    TEXT_NAME_UNSET = 'Имя было отвязано от адреса.'

    def text_set_rune_limit_threshold(self, address, curr_limit):
        return (
            f'🎚 Введите минимальное количество Рун '
            f'для срабатывания уведомлений о переводах на этом адресе ({address}).\n'
            f'Сейчас это: {ital(short_rune(curr_limit))}.\n\n'
            f'Вы можете прислать мне число сообщением или выбрать один из вариантов на кнопках.'
        )

    @staticmethod
    def text_my_wallet_settings(address, name='', min_limit=None):
        name_str = ''
        if name:
            name_str = f' ({ital(name)})'

        if min_limit is not None:
            limit_str = f'\n\n📨 Транзакции ≥ {short_rune(min_limit)} отслеживаются.'
        else:
            limit_str = ''

        return (f'🎚 Настройки кошелька "{code(address)}"{name_str}.'
                f'{limit_str}')

    @staticmethod
    def text_my_wallet_name_changed(address, name):
        return f'🎉 Новое имя установлено "{code(name)}" для кошелька с адресом "{code(address)}".'

    @staticmethod
    def text_wallet_name_dialog(address, name):
        message = (
            f'Для вашего удобства вы можете задать имя для этого адреса ({pre(address)}).\n'
        )
        if name:
            message += f'Текущее имя: "{code(name)}".\n'
        message += '<b>Пожалуйста, отправьте мне сообщение с новым названием для этого адреса</b> 👇'
        return message

    def text_lp_img_caption(self):
        bot_link = "@" + self.this_bot_name
        start_me = self.url_start_me
        return f'Сгенерировано: {link(start_me, bot_link)}'

    LP_PIC_TITLE = 'ликвидность'
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

    def label_for_pool_button(self, pool_name):
        short_name = cut_long_text(pool_name)

        if Asset(pool_name).is_synth:
            return f'Сбер.: {short_name}'
        else:
            return f'Ликв.пр.: {short_name}'

    def pic_lping_days(self, total_days, first_add_ts, extra=''):
        start_date = datetime.fromtimestamp(first_add_ts).strftime('%d.%m.%Y')
        extra = ' ' + extra if extra else ''
        return f'{ceil(total_days)} дн.{extra} ({start_date})'

    TEXT_PLEASE_WAIT = '⏳ <b>Пожалуйста, подождите...</b>'

    def text_lp_loading_pools(self, address):
        return f'{self.TEXT_PLEASE_WAIT}\n' \
               f'Идет загрузка пулов для адреса {pre(address)}...\n' \
               f'Иногда она может идти долго, если Midgard сильно нагружен.'

    @staticmethod
    def text_swapper_clout(clout):
        if not clout:
            return ''
        score_text = pretty_rune(thor_to_float(clout.score))
        reclaimed_text = pretty_rune(thor_to_float(clout.reclaimed))
        spent_text = pretty_rune(thor_to_float(clout.spent))

        clout_text = f'{bold(score_text)} очков | {bold(reclaimed_text)} восстановлено | {bold(spent_text)} потрачено'
        return f'\n\n💪Влиятельность: {clout_text}'

    TEXT_CLICK_FOR_DETAILED_CARD = '\n\n👇 Выберите пул, чтобы получить подробную карточку информации о позиции.'
    TEXT_BALANCE_TITTLE = '💲Балансы кошелька:'
    TEXT_LOCAL_NAME = 'Локальное имя'
    TEXT_TOTAL = 'Всего'

    def text_address_explorer_details(self, address, chain):
        thor_yield_url = get_thoryield_address(address, chain)
        return (
            f"\n\n🔍 Обозреватель: {self.explorer_links_to_address_with_domain(address)}\n"
            f"🌎 Посмотреть на {link(thor_yield_url, 'THORYield')}"
        )

    @staticmethod
    def text_track_limit(min_limit):
        return f'\n\n📨 Транзакции объемом ≥ {short_rune(min_limit)} отслеживаются.' if min_limit is not None else ''

    def text_lp_today(self):
        today = datetime.now().strftime('%d.%m.%Y')
        return f'Сегодня: {today}'

    # ----- CAP ------

    def can_add_more_lp_text(self, cap: ThorCapInfo):
        if cap.can_add_liquidity:
            return (
                f'🤲🏻 Вы можете добавить еще {bold(short_rune(cap.how_much_rune_you_can_lp))} {self.R} '
                f'или {bold(short_dollar(cap.how_much_usd_you_can_lp))}.'
            )
        else:
            return f"🚫 Вы не можете добавить больше ликвидности. Достигнут предел!"

    def notification_text_cap_change(self, old: ThorCapInfo, new: ThorCapInfo):
        up = old.cap < new.cap
        verb = "подрос" if up else "упал"
        arrow = '⬆️' if up else '⚠️ ⬇️'
        call = "Ай-да добавим еще!\n" if up else ''
        return (
            f'{arrow} <b>Кап {verb} с {pretty_money(old.cap)} до {pretty_money(new.cap)}!</b>\n'
            f'Сейчас в пулы помещено <b>{pretty_money(new.pooled_rune)}</b> {self.R}.\n'
            f"{self._cap_progress_bar(new)}\n"
            f"{self.can_add_more_lp_text(new)}\n"
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
            f'Сейчас в пулах <i>{short_rune(cap.pooled_rune)} {self.R}</i> из '
            f"<i>{pretty_money(cap.cap)} {self.R}</i> максимально возможных.\n"
            f"{self._cap_progress_bar(cap)}\n"
            f'🤲🏻 Вы можете еще добавить {bold(short_rune(cap.how_much_rune_you_can_lp))} {self.R} '
            f'или {bold(pretty_dollar(cap.how_much_usd_you_can_lp))}.\n👉🏻 {self.thor_site()}'
        )

    # ------ PRICE -------

    PRICE_GRAPH_TITLE = f'THORChain {RAIDO_GLYPH}une цена'
    PRICE_GRAPH_LEGEND_DET_PRICE = 'Детерминистская цена'
    PRICE_GRAPH_LEGEND_ACTUAL_PRICE = 'Цена в пулах'
    PRICE_GRAPH_LEGEND_CEX_PRICE = f'Цена на бирже'
    PRICE_GRAPH_VOLUME_SWAP_NORMAL = 'Объем обменов'
    PRICE_GRAPH_VOLUME_SWAP_SYNTH = 'Объем синтетиков'
    PRICE_GRAPH_VOLUME_SWAP_TRADE = 'Объем торг. акт.'
    PRICE_GRAPH_VOLUME_SWAP_ADD = 'Объем добавления'
    PRICE_GRAPH_VOLUME_SWAP_WITHDRAW = 'Объем изъятия'

    # ------ TXS -------

    TEXT_MORE_TXS = ' и {n} еще'

    @staticmethod
    def none_str(x):
        return 'нет' if x is None else x

    def notification_text_large_single_tx(self, e: EventLargeTransaction, name_map: NameMap):
        usd_per_rune, pool_info, tx = e.usd_per_rune, e.pool_info, e.transaction

        (ap, asset_side_usd_short, chain, percent_of_pool, pool_depth_usd, rp, rune_side_usd_short,
         total_usd_volume) = self.lp_tx_calculations(usd_per_rune, pool_info, tx)

        heading = ''
        if tx.is_of_type(ActionType.ADD_LIQUIDITY):
            heading = f'🐳→⚡ <b>Добавлена ликвидности</b>'
        elif tx.is_of_type(ActionType.WITHDRAW):
            heading = f'🐳←⚡ <b>Выведена ликвидность</b>'
        elif tx.is_of_type(ActionType.DONATE):
            heading = f'🙌 <b>Пожертвование в пул</b>'
        elif tx.is_of_type(ActionType.SWAP):
            if tx.is_streaming:
                heading = f'🌊 <b>Потоковый обмен завершен</b> 🔁'
            else:
                heading = f'🐳 <b>Крупный обмен</b> 🔁'
        elif tx.is_of_type(ActionType.REFUND):
            heading = f'🐳️ <b>Возврат средств</b> ↩️❗'

        if tx.is_pending:
            heading += ital(' [Ожидает]')

        # it is old
        if date_text := self.tx_date(tx):
            heading += ital(f' {date_text}')

        asset = Asset(tx.first_pool).name

        content = f''

        if tx.is_of_type((ActionType.ADD_LIQUIDITY, ActionType.WITHDRAW, ActionType.DONATE)):
            if tx.affiliate_fee > 0:
                aff_text = f'Партнерский бонус: {format_percent(tx.affiliate_fee, 1)}\n'
            else:
                aff_text = ''

            rune_part = f"{bold(short_money(tx.rune_amount))} {self.R} ({rune_side_usd_short}) ↔️ "
            asset_part = f"{bold(short_money(tx.asset_amount))} {asset} ({asset_side_usd_short})"
            pool_depth_part = f'Глубина пула {bold(short_dollar(pool_depth_usd))} сейчас.'
            pool_percent_part = f" ({percent_of_pool:.2f}% от всего пула)" \
                if percent_of_pool >= self.MIN_PERCENT_TO_SHOW else ''

            content = (
                f"{rune_part}{asset_part}\n"
                f"Всего: <code>${pretty_money(total_usd_volume)}</code>{pool_percent_part}\n"
                f"{aff_text}"
                f"{pool_depth_part}\n"
            )
        elif tx.is_of_type(ActionType.REFUND):
            reason = shorten_text(tx.meta_refund.reason, 180)
            content += (
                    self.format_swap_route(tx, usd_per_rune) +
                    f"\nПричина: {pre(reason)}"
            )
        elif tx.is_of_type(ActionType.SWAP):
            content += self.format_swap_route(tx, usd_per_rune)

            if tx.is_streaming:
                if (success := tx.meta_swap.streaming.success_rate) < 1.0:
                    good = tx.meta_swap.streaming.successful_swaps
                    total = tx.meta_swap.streaming.quantity
                    content += f'\nПроцент успеха: {format_percent(success, 1)} ({good}/{total})'

        user_link = self.link_to_address(tx.sender_address, name_map)
        tx_link = self.link_to_tx(tx.tx_hash)

        msg = (
            f"{heading}\n"
            f"{content}\n"
            f"Пользователь: {user_link}\n"
            f"Транзакция: {tx_link}\n"
            f"{self._conditional_announcement()}"
        )

        return msg.strip()

    def notification_text_streaming_swap_started(self, e: AlertSwapStart, name_map: NameMap):
        user_link = self.link_to_address(e.from_address, name_map)
        track_link = link(self.url_for_tx_tracker(e.tx_id), '👁️‍🗨️Отследить')

        asset_str = Asset(e.in_asset).pretty_str
        amount_str = self.format_op_amount(e.in_amount_float)
        target_asset_str = Asset(e.out_asset).pretty_str

        return (
            f'🌊 <b>Потоковый обмен начался</b>\n'
            f'{amount_str} {asset_str} ({short_dollar(e.volume_usd)}) → ⚡ → {bold(target_asset_str)}\n'
            f'Пользователь: {user_link}\n'
            f'Транзакция: {track_link} | {self.link_to_tx(e.tx_id)}\n'
            f'{self._conditional_announcement()}'
        )

    # ------- QUEUE -------

    def notification_text_queue_update(self, item_type, is_free, value):
        if is_free:
            return f"☺️ Очередь {item_type} снова опустела!"
        else:
            if item_type != 'internal':
                extra = f"\n[{item_type}] транзакции могут запаздывать."
            else:
                extra = ''

            return f"🤬 <b>Внимание!</b> Очередь {code(item_type)} имеет {value} транзакций!{extra}"

    # ------- PRICE -------

    TEXT_PRICE_NO_DATA = 'Извините. Пока что нет данных о цене. Попробуйте позже.'

    def notification_text_price_update(self, p: AlertPrice):
        title = bold('Обновление цены') if not p.is_ath else bold('🚀 Достигнуть новый исторический максимум!')

        c_gecko_link = link(self.COIN_GECKO_URL, 'RUNE')

        message = f"{title} | {c_gecko_link}\n\n"

        price = p.market_info.pool_rune_price

        btc_price = f"₿ {p.btc_pool_rune_price:.8f}"
        pr_text = f"${price:.3f}"
        message += f"Цена <b>RUNE</b> сейчас {code(pr_text)} ({btc_price}).\n"

        message += f'\n{self.TEXT_REF_CALL}'

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
                extra = '🎉 ПУЛ АКТИВИРОВАН!'
            else:
                extra = ital(ru_stat.get(str(status).lower(), ''))
                if to_status is not None:
                    to_stat_str = ital(ru_stat.get(str(to_status).lower(), ''))
                    extra += f' → {to_stat_str}'
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

    TEXT_SETTING_INTRO = '<b>Настройки</b>\nЧто вы хотите поменять в настройках?'
    BUTTON_SET_LANGUAGE = '🌐 Язык'
    BUTTON_SET_NODE_OP_GOTO = '🖥 Операторам нод'
    BUTTON_SET_PRICE_DIVERGENCE = '↕️ Расхождение цен'

    TEXT_SETTINGS_LANGUAGE_SELECT = 'Пожалуйста, выберите язык / Please select a language'

    # ------- PERSONAL PRICE DIVERGENCE -------

    TEXT_PRICE_DIV_MIN_PERCENT = (
        '↕️ Здесь вы можете настроить ваши персональные уведомления о расхождении цен Руны на бирже и Руны в пулах.\n'
        'Для начала введите <b>минимальный</b> процент отклонения (<i>не может быть меньше, чем 0.1</i>).\n'
        'Если вы, не хотите получать уведомления с минимальной стороны, просто нажмите "Далее"'
    )

    BUTTON_PRICE_DIV_NEXT = 'Далее ⏭️'
    BUTTON_PRICE_DIV_TURN_OFF = 'Выключить 📴'

    TEXT_PRICE_DIV_TURNED_OFF = 'Уведомления о расхождении цен выключены.'

    TEXT_PRICE_DIV_MAX_PERCENT = (
        'Хорошо!\n'
        'А теперь введите <b>максимальный</b> процент отклонения (<i>не более 100%</i>).\n'
        'Если вы не хотите уведомлений с максимальной стороны, нажмите "Далее"'
    )

    TEXT_PRICE_DIV_INVALID_NUMBER = '<code>Не правильное число!</code> Попробуйте еще раз.'

    @staticmethod
    def text_price_div_finish_setup(min_percent, max_percent):
        message = '✔️ Готово!\n'
        if min_percent is None and max_percent is None:
            message += '🔘 Вы <b>не</b> будете получать уведомления о расхождении цен.'
        else:
            message += 'Ваши триггеры:\n'
            if min_percent:
                message += f'→ Расхождение цен Рун &lt;= {pretty_money(min_percent)}%\n'
            if max_percent:
                message += f'→ Расхождение цен Рун &gt;= {pretty_money(max_percent)}%\n'
        return message.strip()

    def notification_text_price_divergence(self, e: AlertPriceDiverge):
        title = f'〰 Низкое расхождение цены!' if e.below_min_divergence else f'🔺 Высокое расхождение цены!'

        div, div_p = e.info.divergence_abs, e.info.divergence_percent
        text = (
            f"🖖 {bold(title)}\n"
            f"Цена Руны (на биржах): {code(pretty_dollar(e.info.cex_price))}\n"
            f"Взвешенная цена Руны в пулах: {code(pretty_dollar(e.info.pool_rune_price))}\n"
            f"<b>Расхождение</b> цены THORChain и биржи: {code(pretty_dollar(div))} ({div_p:.1f}%)."
        )

        return text

    # -------- METRICS ----------

    BUTTON_METR_S_FINANCIAL = '💱 Финансовые'
    BUTTON_METR_S_NET_OP = '🔩 Работа сети'

    BUTTON_METR_CAP = '✋ Кап ликвидности'
    BUTTON_METR_PRICE = f'💲 {BaseLocalization.R} инфо о цене'
    BUTTON_METR_QUEUE = f'👥 Очередь'
    BUTTON_METR_STATS = f'📊 Статистика'
    BUTTON_METR_NODES = '🖥 Ноды (узлы)'
    BUTTON_METR_LEADERBOARD = '🏆 Доска рекордов'
    BUTTON_METR_CHAINS = '⛓️ Блокчейны'
    BUTTON_METR_MIMIR = '🎅 Мимир'
    BUTTON_METR_VOTING = '🏛️ Голосование'
    BUTTON_METR_TOP_POOLS = '🏊 Топ Пулов'
    BUTTON_METR_CEX_FLOW = '🌬 Поток бирж'
    BUTTON_METR_SUPPLY = f'🪙 Rune предложение'
    BUTTON_METR_DEX_STATS = f'🤹 DEX Агр. статы'
    BUTTON_METR_SECURED = f'🔐 Секьюред активы'

    TEXT_METRICS_INTRO = 'Что вы хотите узнать?'

    def cap_message(self, info: ThorCapInfo):
        return (
            f"<b>{pretty_money(info.pooled_rune)} {RAIDO_GLYPH} {self.R}</b> монет из "
            f"<b>{pretty_money(info.cap)} {RAIDO_GLYPH} {self.R}</b> сейчас в пулах.\n"
            f"{self._cap_progress_bar(info)}\n"
            f"{self.can_add_more_lp_text(info)}\n"
            f"Цена {bold(self.R)} сейчас <code>{info.price:.3f} $</code>.\n"
        )

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

    TEXT_ASK_DURATION = 'За какой период времени вы хотите получить данные?'

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
                     'Скачай это фото и установи его в Telegram и социальных сетях.'

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
            return "🤬 ПОТЕНЦИАЛЬНО НЕБЕЗОПАСНА"

    def notification_text_network_summary(self, e: AlertNetworkStats):
        new, old, nodes = e.new, e.old, e.nodes

        message = bold('🌐 THORChain статистика') + '\n\n'

        # --------------- NODES / SECURITY --------------------

        sec_ratio = self.get_network_security_ratio(new, nodes)
        if sec_ratio > 0:
            # security_pb = progressbar(sec_ratio, 1.0, 12)
            security_text = self.network_bond_security_text(sec_ratio)
            message += f'🕸️ Сейчас сеть {bold(security_text)}.\n'

        active_nodes_change = bracketify(up_down_arrow(old.active_nodes, new.active_nodes, int_delta=True))
        standby_nodes_change = bracketify(up_down_arrow(old.active_nodes, new.active_nodes, int_delta=True))
        message += f"🖥️ {bold(new.active_nodes)} активных нод{active_nodes_change} " \
                   f"и {bold(new.standby_nodes)} нод в режиме ожидания{standby_nodes_change}.\n"

        # --------------- NODE BOND --------------------

        current_bond_text = bold(short_rune(new.total_active_bond_rune))
        current_bond_change = bracketify(
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

        message += f"🔗 Бонд активных нод: {current_bond_text}{current_bond_change} или " \
                   f"{current_bond_usd_text}{current_bond_usd_change}.\n"

        message += f"🔗 Бонд всех нод: {current_total_bond_text}{current_total_bond_change} или " \
                   f"{current_total_bond_usd_text}{current_total_bond_usd_change}.\n"

        # --------------- POOLED RUNE --------------------

        current_pooled_text = bold(short_rune(new.total_rune_lp))
        current_pooled_change = bracketify(
            up_down_arrow(old.total_rune_lp, new.total_rune_lp, money_delta=True))

        current_pooled_usd_text = bold(short_dollar(new.total_pooled_usd))
        current_pooled_usd_change = bracketify(
            up_down_arrow(old.total_pooled_usd, new.total_pooled_usd, money_delta=True, money_prefix='$'))

        message += f"🏊 Всего в пулах: {current_pooled_text}{current_pooled_change} или " \
                   f"{current_pooled_usd_text}{current_pooled_usd_change}.\n"

        # ----------------- LIQUIDITY / BOND / RESERVE --------------------------------

        current_liquidity_usd_text = bold(short_dollar(new.total_liquidity_usd))
        current_liquidity_usd_change = bracketify(
            up_down_arrow(old.total_liquidity_usd, new.total_liquidity_usd, money_delta=True, money_prefix='$'))

        message += f"🌊 Всего ликвидности (TVL): {current_liquidity_usd_text}{current_liquidity_usd_change}.\n"

        tlv_change = bracketify(
            up_down_arrow(old.total_locked_usd, new.total_locked_usd, money_delta=True, money_prefix='$'))
        message += f'🏦 TVL + бонды нод: {code(short_dollar(new.total_locked_usd))}{tlv_change}.\n'

        reserve_change = bracketify(up_down_arrow(old.reserve_rune, new.reserve_rune,
                                                  postfix=RAIDO_GLYPH, money_delta=True))
        message += f'💰 Резервы: {bold(short_rune(new.reserve_rune))}{reserve_change}.\n'

        # ----------------- ADD/WITHDRAW STATS -----------------

        message += '\n'
        message += f'{ital(f"За последние сутки:")}\n'

        price = new.usd_per_rune

        if old.is_ok:
            # 24 h Add/withdrawal
            added_24h_rune = new.added_rune - old.added_rune
            withdrawn_24h_rune = new.withdrawn_rune - old.withdrawn_rune

            add_rune_text = bold(short_rune(added_24h_rune))
            withdraw_rune_text = bold(short_rune(withdrawn_24h_rune))

            add_usd_text = short_dollar(added_24h_rune * price)
            withdraw_usd_text = short_dollar(withdrawn_24h_rune * price)

            if added_24h_rune:
                message += f'➕ Добавлено в пулы: {add_rune_text} ({add_usd_text}).\n'

            if withdrawn_24h_rune:
                message += f'➖ Выведено из пулов: {withdraw_rune_text} ({withdraw_usd_text}).\n'

            message += '\n'

        synth_volume_usd = code(short_dollar(new.synth_volume_24h_usd))
        synth_op_count = short_money(new.synth_op_count)

        trade_volume_usd = code(short_dollar(new.trade_volume_24h_usd))
        trade_op_count = short_money(new.trade_op_count)

        swap_usd_text = code(short_dollar(new.swap_volume_24h_usd))
        swap_op_count = bold(short_money(new.swaps_24h))

        message += f'🔀 Всего объемы: {swap_usd_text} за {swap_op_count} операций.\n'
        message += f'🆕 Объемы торговых активов {trade_volume_usd} за {trade_op_count} операций.\n'
        message += f'Объем торговли синтетиками {synth_volume_usd} за {synth_op_count} операций.\n'

        # ---------------- APY -----------------

        message += '\n'

        bonding_apy_change, liquidity_apy_change = self._extract_apy_deltas(new, old)
        message += (
            f'📈 Доход от бондов в нодах, годовых: '
            f'{code(pretty_money(new.bonding_apy, postfix="%"))}{bonding_apy_change} и '
            f'доход от пулов в среднем, годовых: '
            f'{code(pretty_money(new.liquidity_apy, postfix="%"))}{liquidity_apy_change}.\n'
        )

        # ---------------- USER STATS -----------------

        if new.users_daily or new.users_monthly:
            daily_users_change = bracketify(up_down_arrow(old.users_daily, new.users_daily, int_delta=True))
            monthly_users_change = bracketify(up_down_arrow(old.users_monthly, new.users_monthly, int_delta=True))
            message += f'👥 Пользователей за день: {code(new.users_daily)}{daily_users_change}, ' \
                       f'пользователей за месяц: {code(new.users_monthly)}{monthly_users_change} 🆕\n'
            message += '\n'

        # ---------------- POOLS -----------------

        active_pool_changes = bracketify(up_down_arrow(old.active_pool_count,
                                                       new.active_pool_count, int_delta=True))
        pending_pool_changes = bracketify(up_down_arrow(old.pending_pool_count,
                                                        new.pending_pool_count, int_delta=True))
        message += f'{bold(new.active_pool_count)} активных пулов{active_pool_changes}.\n'
        message += f'{bold(new.pending_pool_count)} ожидающих активации пулов{pending_pool_changes}.\n'

        if new.next_pool_to_activate:
            next_pool_wait = self.seconds_human(new.next_pool_activation_ts - now_ts())
            next_pool = self.pool_link(new.next_pool_to_activate)
            message += f"Вероятно, будет активирован пул: {next_pool} через {next_pool_wait}."
        else:
            message += f"Пока что нет достойного пула для активации."

        return message

    # Translate to Russian
    TEXT_PIC_STATS_NATIVE_ASSET_VAULTS = "Нативные Активы в хранилищах"
    TEXT_PIC_STATS_WEEKLY_REVENUE = "Недельный доход протокола"
    TEXT_PIC_STATS_SWAP_INFO = "Информация о свопах за неделю"

    TEXT_PIC_STATS_NATIVE_ASSET_POOLED = 'Всего нативных активов'
    TEXT_PIC_STATS_NETWORK_SECURITY = 'Безопасность сети'
    TEXT_PIC_STATS_PROTOCOL_REVENUE = 'Доход протокола'
    TEXT_PIC_STATS_AFFILIATE_REVENUE = 'Доход партнеров'
    TEXT_PIC_STATS_TOP_AFFILIATE = 'Топ 3 партнера по доходу'
    TEXT_PIC_STATS_UNIQUE_SWAPPERS = 'Уникальных трейдеров'
    TEXT_PIC_STATS_NUMBER_OF_SWAPS = 'Количество обменов'
    TEXT_PIC_STATS_USD_VOLUME = 'Объем торгов'
    TEXT_PIC_STATS_TOP_SWAP_ROUTES = 'Топ 3 пути обмена'
    TEXT_PIC_STATS_ORGANIC_VS_BLOCK_REWARDS = 'Комиссии / награды блока'

    TEXT_PIC_STATS_SYNTH = 'синты'
    TEXT_PIC_STATS_TRADE = 'торг.'
    TEXT_PIC_STATS_NORMAL = 'обычные'

    @staticmethod
    def text_key_stats_period(start_date: datetime, end_date: datetime):
        date_format = '%d %B %Y'

        month_names = {
            "January": "Января",
            "February": "Февраля",
            "March": "Марта",
            "April": "Апреля",
            "May": "Мая",
            "June": "Июня",
            "July": "Июля",
            "August": "Августа",
            "September": "Сентября",
            "October": "Октября",
            "November": "Ноября",
            "December": "Декабря"
        }

        return translate(f'{start_date.strftime(date_format)} – {end_date.strftime(date_format)}', month_names)

    def notification_text_key_metrics_caption(self, data: AlertKeyStats):
        return 'THORChain недельная статистика'

    TEXT_WEEKLY_STATS_NO_DATA = '😩 Нет данных по статистике за этот период.'

    # ------ TRADE ACCOUNT ------

    def notification_text_trade_account_move(self, event: AlertTradeAccountAction, name_map: NameMap):
        action_str = 'Депозит на торговый счет' if event.is_deposit else 'Вывод с торгового счета'
        from_link, to_link, amt_str = self._trade_acc_from_to_links(event, name_map)
        arrow = '➡' if event.is_deposit else '⬅'
        return (
            f"{arrow}🏦 <b>{action_str}</b>\n"
            f"От {from_link} на {to_link}\n"
            f"Всего: {amt_str}\n"
            f"{self.link_to_tx(event.tx_hash)}"
        )

    def notification_text_trade_account_summary(self, e: AlertTradeAccountStats):
        top_n = 5
        top_vaults_str = self._top_trade_vaults(e, top_n)

        delta_holders = bracketify(
            up_down_arrow(e.prev.vaults.total_traders, e.curr.vaults.total_traders, int_delta=True)) if e.prev else ''

        delta_balance = bracketify(
            up_down_arrow(e.prev.vaults.total_usd, e.curr.vaults.total_usd, percent_delta=True)) if e.prev else ''

        tr_swap_volume_curr, tr_swap_volume_prev = e.curr_and_prev_trade_volume_usd
        delta_volume = bracketify(
            up_down_arrow(tr_swap_volume_prev, tr_swap_volume_curr, percent_delta=True)) if e.prev else ''

        return (
            f"⚖️ <b>Сводка по торговым счетам за сутки</b>\n"
            f"Всего держателей: {bold(pretty_money(e.curr.vaults.total_traders))}"
            f" {delta_holders}\n"
            f"Всего торговых активов: {bold(short_money(e.curr.vaults.total_usd))}"
            f" {delta_balance}\n"
            f"Депозиты: {bold(short_money(e.curr.trade_deposit_count, integer=True))}"
            f" {bracketify(short_dollar(e.curr.trade_deposit_vol_usd))}\n"
            f"Выводы: {bold(short_money(e.curr.trade_withdrawal_count, integer=True))}"
            f" {bracketify(short_dollar(e.curr.trade_withdrawal_vol_usd))}\n"
            f"Объем торгов: {bold(short_dollar(tr_swap_volume_curr))} {delta_volume}\n"
            f"Количество обменов: {bold(short_money(e.curr.trade_swap_count, integer=True))}"
            f" {bracketify(up_down_arrow(e.prev.trade_swap_count, e.curr.trade_swap_count, int_delta=True))}\n"
            f"\n"
            f"Наиболее используемые:\n"
            f"{top_vaults_str}"
        )

    # ------- NETWORK NODES -------

    TEXT_PIC_NODES = 'ноды'
    TEXT_PIC_ACTIVE_NODES = 'Активные'
    TEXT_PIC_STANDBY_NODES = 'Ожидающие'
    TEXT_PIC_ALL_NODES = 'Все ноды'
    TEXT_PIC_NODE_DIVERSITY = 'Распределение нод'
    TEXT_PIC_NODE_DIVERSITY_SUBTITLE = 'по провайдеру инфраструктуры'
    TEXT_PIC_OTHERS = 'Другие'
    TEXT_PIC_UNKNOWN = 'Не известно'

    TEXT_PIC_UNKNOWN_LOCATION = 'Неизвестное положение'
    TEXT_PIC_CLOUD = 'Облако'
    TEXT_PIC_COUNTRY = 'Страна'
    TEXT_PIC_ACTIVE_BOND = 'Активный бонд'
    TEXT_PIC_TOTAL_NODES = 'Всего нод'
    TEXT_PIC_TOTAL_BOND = 'Общий бонд'
    TEXT_PIC_MIN_BOND = 'Мин. бонд'
    TEXT_PIC_MEDIAN_BOND = 'Медиана'
    TEXT_PIC_MAX_BOND = 'Макс'

    def _format_node_text(self, node: NodeInfo, add_status=False, extended_info=False, expand_link=False):
        if expand_link:
            node_ip_link = link(get_ip_info_link(node.ip_address), node.ip_address) if node.ip_address else 'No IP'
        else:
            node_ip_link = node.ip_address or 'no IP'

        thor_explore_url = get_explorer_url_to_address(self.cfg.network_id, Chains.THOR, node.node_address)
        node_thor_link = link(thor_explore_url, short_address(node.node_address, 0))

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

        status = f', ({status})' if add_status else ''
        version_str = f", v. {node.version}" if extended_info else ''
        return f'{bold(node_thor_link)} ({node.flag_emoji}{node_ip_link}{version_str}) ' \
               f'с {bold(pretty_money(node.bond, postfix=RAIDO_GLYPH))} бонд {status}{extra}'.strip()

    def _node_bond_change_after_churn(self, changes: NodeSetChanges):
        bond_in, bond_out = changes.bond_churn_in, changes.bond_churn_out
        bond_delta = bond_in - bond_out
        return f'Изменение активного бонда: {code(short_money(bond_delta, postfix=RAIDO_GLYPH, signed=True))}'

    def notification_text_node_churn_finish(self, changes: NodeSetChanges):
        message = ''

        if changes.nodes_activated or changes.nodes_deactivated:
            message += bold('♻️ Перемешивание нод завершено') + '\n'

        if changes.nodes_activated or changes.nodes_deactivated:
            message += self._node_bond_change_after_churn(changes) + '\n'

        if changes.churn_duration:
            message += f'Продолжительность: {seconds_human(changes.churn_duration)}\n'

        message += '\n'

        # message += self._make_node_list(changes.nodes_added, '🆕 Новые ноды появились:', add_status=True)
        message += self._make_node_list(changes.nodes_activated, '➡️ Ноды активированы:')
        message += self._make_node_list(changes.nodes_deactivated, '⬅️️ Ноды деактивированы:')
        # message += self._make_node_list(changes.nodes_removed, '🗑️ Ноды отключились или исчезли:', add_status=True)

        return message.strip()

    def notification_churn_started(self, changes: NodeSetChanges):
        text = f'♻️ <b>Процесс перемешивания нод начался на блоке #{changes.block_no}</b>'
        if changes.vaults_migrating:
            text += '\nХранилища мигрируют.'
        return text

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

    def notification_text_version_changed_progress(self, e: AlertVersionUpgradeProgress):
        msg = bold('🕖 Прогресс обновления протокола THORChain\n\n')

        progress = e.ver_con.ratio * 100.0
        pb = progressbar(progress, 100.0, 14)

        msg += f'{pb} {progress:.0f} %\n'
        msg += f"{pre(e.ver_con.top_version_count)} из {pre(e.ver_con.total_active_node_count)} нод " \
               f"обновились до версии {pre(e.ver_con.top_version)}\n\n"

        cur_version_txt = self.node_version(e.data.current_active_version, e.data, active=True)
        msg += f"⚡️ Активная версия протокола сейчас – {cur_version_txt}\n" + \
               ital('* Это минимальная версия среди всех активных нод.') + '\n\n'

        return msg

    def notification_text_version_changed(self, e: AlertVersionChanged):
        msg = bold('💫 Обновление версии протокола THORChain') + '\n\n'

        def version_and_nodes(v, _all=False):
            realm = e.data.nodes_all if _all else e.data.active_only_nodes
            n_nodes = len(e.data.find_nodes_with_version(realm, v))
            return f"{code(v)} ({n_nodes} {plural(n_nodes, 'нода', 'нод')})"

        current_active_version = e.data.current_active_version

        if e.new_versions:
            new_version_joined = ', '.join(version_and_nodes(v, _all=True) for v in e.new_versions)
            msg += f"🆕 Обнаружена новая версия: {new_version_joined}\n\n"

            msg += f"⚡️ Активная версия протокола сейчас – {version_and_nodes(current_active_version)}\n" + \
                   ital('* Это минимальная версия среди всех активных нод.') + '\n\n'

        if e.old_active_ver != e.new_active_ver:
            action = 'улучшилась' if e.new_active_ver > e.old_active_ver else 'откатилась'
            emoji = '🆙' if e.new_active_ver > e.old_active_ver else '⬇️'
            msg += (
                f"{emoji} {bold('Внимание!')} Активная версия протокола {bold(action)} "
                f"с версии {pre(e.old_active_ver)} "
                f"до версии {version_and_nodes(e.new_active_ver)}\n\n"
            )

            cnt = e.data.version_counter(e.data.active_only_nodes)
            if len(cnt) == 1:
                msg += f"Все активные ноды имеют версию {code(current_active_version)}\n"
            elif len(cnt) > 1:
                msg += bold(f"Самые популярные версии нод:") + '\n'
                for i, (v, count) in enumerate(cnt.most_common(5), start=1):
                    active_node = ' 👈' if v == current_active_version else ''
                    msg += f"{i}. {version_and_nodes(v)} {active_node}\n"
                msg += f"Максимальная доступная версия – {version_and_nodes(e.data.max_available_version)}\n"

        return msg

    # --------- CHAIN INFO SUMMARY ------------

    def text_chain_info(self, chain_infos: List[ThorChainInfo]):
        text = '⛓️ ' + bold('THORChain подключен к блокчейнам:') + '\n\n'
        for c in chain_infos:
            address_link = link(get_explorer_url_to_address(self.cfg.network_id, c.chain, c.address), 'СКАН')
            status = '🛑 Остановлен' if c.halted else '🆗 Активен'
            text += f'{bold(c.chain)}:\n' \
                    f'Статус: {status}\n' \
                    f'Входящий адрес: {pre(c.address)} | {address_link}\n'

            if c.router:
                router_link = link(get_explorer_url_to_address(self.cfg.network_id, c.chain, c.router), 'СКАН')
                text += f'Роутер: {pre(c.router)} | {router_link}\n'

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
    MIMIR_UNTIL_BLOCK = 'до блока'
    MIMIR_DISABLED = 'ВЫКЛЮЧЕНО'
    MIMIR_YES = 'ДА'
    MIMIR_NO = 'НЕТ'
    MIMIR_UNDEFINED = 'не определено'
    MIMIR_LAST_CHANGE = 'Последнее изменение'
    MIMIR_UNKNOWN_CHAIN = 'Неизв. сеть'

    def text_mimir_intro(self):
        text = f'🎅 {bold("Глобальные константы и Мимир")}\n'
        cheatsheet_link = link(self.MIMIR_CHEAT_SHEET_URL, 'Описание констант')
        what_is_mimir_link = link(self.MIMIR_DOC_LINK, "Что такое Мимир?")
        text += f"{what_is_mimir_link} А еще {cheatsheet_link}.\n\n"
        return text

    TEXT_NODE_MIMIR_VOTING_TITLE = '🏛️ <b>Голосование нод за Мимир</b>\n\n'
    TEXT_NODE_MIMIR_VOTING_NOTHING_YET = 'Пока нет активных голосований.'
    TEXT_NODE_MIMIR_ALREADY_CONSENSUS = '✅'

    TEXT_MIMIR_CURR_VAL = 'Текущее значение'

    def _text_votes_to_pass(self, option):
        show = 0 < option.need_votes_to_pass <= self.NEED_VOTES_TO_PASS_MAX
        return f' {option.need_votes_to_pass} еще голосов, чтобы прошло' if show else ''

    TEXT_MIMIR_VOTING_PROGRESS_TITLE = '🏛 <b>Прогресс голосования нод за Мимир</b>\n\n'
    TEXT_MIMIR_VOTING_TO_SET_IT = 'чтобы стало'

    # --------- TRADING HALTED -----------

    def notification_text_trading_halted_multi(self, chain_infos: List[ThorChainInfo]):
        msg = ''

        halted_chains = ', '.join(c.chain for c in chain_infos if c.halted)
        if halted_chains:
            msg += f'🚨🚨🚨 <b>Внимание!</b> Торговля остановлена на {code(halted_chains)}! ' \
                   f'Воздержитесь от обменов, пока торговля не будет снова запущена! 🚨🚨🚨\n\n'

        resumed_chains = ', '.join(c.chain for c in chain_infos if not c.halted)
        if resumed_chains:
            msg += f'✅ <b>Внимание!</b> Торговля снова возобновлена на блокчейнах: {code(resumed_chains)}!'

        return msg.strip()

    # ---------- BLOCK HEIGHT -----------

    TEXT_BLOCK_HEIGHT_CHART_TITLE = 'THORChain блоков в минут'
    TEXT_BLOCK_HEIGHT_LEGEND_ACTUAL = 'Фактически блоков в минуту'
    TEXT_BLOCK_HEIGHT_LEGEND_EXPECTED = 'Ожидаемая (10 бл/мин или 6 сек на блок)'

    def notification_text_block_stuck(self, e: EventBlockSpeed):
        good_time = e.time_without_blocks is not None and e.time_without_blocks > 1
        str_t = ital(self.seconds_human(e.time_without_blocks) if good_time else self.NA)
        if e.state == BlockProduceState.StateStuck:
            return f'📛 {bold("THORChain высота блоков перестала увеличиваться")}!\n' \
                   f'Новые блоки не генерируются уже {str_t}.'
        else:
            return f"🆗 {bold('THORChain снова генерирует блоки!')}\n" \
                   f"Сбой длился {str_t}"

    @staticmethod
    def get_block_time_state_string(state, state_changed):
        if state == BlockProduceState.NormalPace:
            if state_changed:
                return '👌 Скорость генерации блоков вернулась к нормальной.'
            else:
                return '👌 Скорость генерации блоков в норме.'
        elif state == BlockProduceState.TooSlow:
            return '🐌 Блоки производятся слишком медленно.'
        elif state == BlockProduceState.TooFast:
            return '🏃 Блоки производятся слишком быстро.'
        else:
            return ''

    def notification_text_block_pace(self, e: EventBlockSpeed):
        phrase = self.get_block_time_state_string(e.state, True)
        block_per_minute = self.format_bps(e.block_speed)

        return (
            f'<b>Обновление по скорости производства блоков THORChain</b>\n'
            f'{phrase}\n'
            f'В настоящий момент <code>{block_per_minute}</code> блоков в минуту, другими словами '
            f'нужно <code>{self.format_block_time(e.block_speed)} сек</code> на создание блока.'
        )

    def text_block_time_report(self, last_block, last_block_ts, recent_bps, state):
        phrase = self.get_block_time_state_string(state, False)
        block_per_minute = self.format_bps(recent_bps)
        ago = self.format_time_ago(last_block_ts)
        block_str = f"#{last_block}"
        return (
            f'<b>THORChain темпы производства блоков.</b>\n'
            f'{phrase}\n'
            f'В настоящее время <code>{block_per_minute}</code> блоков в минуту, другими словами'
            f'нужно <code>{self.format_block_time(block_per_minute)} сек</code> на создание блока.\n'
            f'Последний номер блока THORChain: {code(block_str)} (обновлено: {ago}).'
        )

    # --------- MIMIR CHANGED -----------

    def notification_text_mimir_changed(self, changes: List[MimirChange], mimir: MimirHolder):
        if not changes:
            return ''

        text = '🔔 <b>Обновление Мимир!</b>\n\n'

        for change in changes:
            old_value_fmt, new_value_fmt = self._old_and_new_mimir(change, mimir)
            old_value_fmt = code(old_value_fmt)
            new_value_fmt = code(new_value_fmt)

            name = code(change.entry.pretty_name if change.entry else change.name)

            e = change.entry
            if e:
                if e.source == e.SOURCE_AUTO:
                    text += bold('[🤖 Автоматика]  ')
                elif e.source == e.SOURCE_ADMIN:
                    # text += bold('[👩‍💻 Администраторы ]  ')
                    pass  # todo
                elif e.source == e.SOURCE_NODE:
                    text += bold('[🤝 Голосование нод ]  ')
                elif e.source == e.SOURCE_NODE_PAUSE:
                    text += bold('[⏸️] ')
                elif e.source == e.SOURCE_NODE_CEASED:
                    text += bold('[💔 Мимир нод отменен ]  ')

            if change.kind == MimirChange.ADDED_MIMIR:
                text += (
                    f'➕ Настройка "{name}" теперь переопределена новым Мимиром. '
                    f'Старое значение по умолчанию было: {old_value_fmt} → '
                    f'новое значение стало: {new_value_fmt}'
                )
            elif change.kind == MimirChange.REMOVED_MIMIR:
                text += f'➖ Настройка Мимира "{name}" была удалена! Ранее она имела значение: {old_value_fmt}.'
                if change.new_value is not None:
                    text += f' Теперь она вернулась к исходной константе: {new_value_fmt}'
            else:
                text += (
                    f'Настройка Мимира "{name}" была изменена. '
                    f'Старое значение: {old_value_fmt} → '
                    f'новое значение теперь: {new_value_fmt}'
                )
                if change.entry.automatic and change.non_zero_value:
                    text += f' (на блоке #{ital(change.non_zero_value)}).'
            text += '\n\n'

        text += link("https://docs.thorchain.org/how-it-works/governance#mimir", "Что такое Mimir?")

        return text

    # ------- NODE OP TOOLS -------

    BUTTON_NOP_ADD_NODES = '➕ Добавь ноды'
    BUTTON_NOP_MANAGE_NODES = '🖊️ Редактировать'
    BUTTON_NOP_SETTINGS = '⚙️ Настройки'
    BUTTON_NOP_GET_SETTINGS_LINK = '⚙️ Настройка на сайте New!'

    def pretty_node_desc(self, node: NodeInfo, name=None):
        addr = self.short_node_name(node.node_address, name)
        return f'{pre(addr)} ({bold(short_money(node.bond, prefix="R"))} бонд)'

    TEXT_NOP_INTRO_HEADING = bold('Добро пожаловать в Инстременты Операторов Нод.')

    def text_node_op_welcome_text_part2(self, watch_list: list, last_signal_ago: float):
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

        mon_link = 'https://thornode.network/nodes'
        text += f'\n\nМониторинг реальном времени: {link(mon_link, mon_link)}'

        return text

    TEXT_NOP_MANAGE_LIST_TITLE = \
        'Вы добавили <b>{n}</b> нод в ваш список слежения. ' \
        'Вы можете убрать ноды из списка слежения, нажав на кнопки снизу.'

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

    def text_nop_get_weblink_title(self, _link):
        return f'Ваша ссылка для настройки готова: {_link}!\n' \
               f'Там вы сможете выбрать ноды для мониторинга и настроить уведомления.'

    BUTTON_NOP_SETT_OPEN_WEB_LINK = '🌐 Открыть в браузере'
    BUTTON_NOP_SETT_REVOKE_WEB_LINK = '🤜 Отозвать ссылку'

    TEXT_NOP_REVOKED_URL_SUCCESS = 'Ссылка для настроек и токен были отозваны!'

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
               f'<i>На следующем шаге вы настроите уведомления об обновлении ваших нод.</i>'

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
        node_addresses_text = shorten_text(node_addresses_text, 80)
        message = f'😉 Успех! {node_addresses_text} добавлены в ваш список. ' \
                  f'Ожидайте уведомлений, если произойдет что-то важное!'
        return message

    BUTTON_NOP_CLEAR_LIST = '🗑️ Очистить все ({n})'
    BUTTON_NOP_REMOVE_INACTIVE = '❌ Убрать неактивные ({n})'
    BUTTON_NOP_REMOVE_DISCONNECTED = '❌ Убрать отключенные ({n})'

    def text_nop_success_remove_banner(self, node_addresses):
        node_addresses_text = ','.join([self.short_node_name(a) for a in node_addresses])
        node_addresses_text = shorten_text(node_addresses_text, 120)
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
        elif c.type == NodeEventType.BOND:
            old, new = c.data
            message = f'⚖️ Нода {short_addr}: изменение бонда с ' \
                      f'{pretty_rune(old)} ' \
                      f'до {bold(pretty_rune(new))}!'
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
        elif c.type == NodeEventType.BLOCK_HEIGHT:
            data: EventBlockHeight = c.data

            if data.is_sync:
                message = f'✅ Нода {short_addr} догнала актуальные блоки на блокчейне {pre(data.chain)}.'
            else:
                message = f'🔴 Нода {short_addr} на {pre(data.block_lag)} позади ' \
                          f'на блокчейне {pre(data.chain)} (≈{self.seconds_human(data.how_long_behind)})!'
        elif c.type == NodeEventType.PRESENCE:
            if c.data:
                message = f'🙋 Нода {short_addr} снова вернулась в сеть THORChain!'
            else:
                message = f'⁉️ Нода {short_addr} исчезла из сети THORChain!'
        elif c.type == NodeEventType.TEXT_MESSAGE:
            text = str(c.data)[:self.NODE_OP_MAX_TEXT_MESSAGE_LENGTH]
            message = f'⚠️ Сообщение всем: {code(text)}'
        elif c.type == NodeEventType.CABLE_DISCONNECT:
            message = f'💔️ NodeOp инструменты <b>отключились</b> от сети THORChain.\n' \
                      f'Пожалуйста, воспользуйтсь альтернативными сервисами для мониторинга нод, ' \
                      f'пока мы не исправим проблему.'
        elif c.type == NodeEventType.CABLE_RECONNECT:
            message = f'💚 NodeOp инструменты снова подключились к THORChain.'

        return message

    # ------- BEST POOLS -------

    TEXT_BP_HEADER = 'ЛУЧШИЕ ПУЛЫ'

    TEXT_BP_INCOME_TITLE = 'ДОХОД НЕДЕЛИ'
    TEXT_BP_HIGH_VOLUME_TITLE = 'ОБЪЕМЫ 24ч'
    TEXT_BP_DEEPEST_TITLE = 'ГЛУБИНА'

    TEXT_BP_ACTIVE_POOLS = 'Активные пулы'
    TEXT_BP_REVENUE = 'Недельная доходность'
    TEXT_BP_TOTAL_LIQ = 'Общая ликвидность'
    TEXT_BP_24H_VOLUME = 'Объем за 24 часа'

    def notification_text_best_pools(self, pd: EventPools):
        return 'Топ пулов ликвидности THORChain'

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
        'month': 'мес',
        'months': 'мес',
        'ago': 'назад',
    }

    def format_time_ago(self, d):
        return format_time_ago(d, translate=self.DATE_TRANSLATOR)

    def seconds_human(self, s):
        return seconds_human(s, translate=self.DATE_TRANSLATOR)

    # ----- RUNE FLOW ------

    def notification_text_cex_flow(self, cex_flow: RuneCEXFlow):
        emoji = self.cex_flow_emoji(cex_flow)
        period_string = self.format_period(cex_flow.period_sec)
        return (
            f'🌬️ <b>Rune потоки с централизованных бирж последние {period_string}</b>\n'
            f'➡️ Завели: {pre(short_money(cex_flow.rune_cex_inflow, postfix=RAIDO_GLYPH))} '
            f'({short_dollar(cex_flow.in_usd)})\n'
            f'⬅️ Вывели: {pre(short_money(cex_flow.rune_cex_outflow, postfix=RAIDO_GLYPH))} '
            f'({short_dollar(cex_flow.out_usd)})\n'
            f'{emoji} Поток на биржи: '
            f'{pre(short_money(cex_flow.rune_cex_netflow, postfix=RAIDO_GLYPH, signed=True))} '
            f'({short_dollar(cex_flow.netflow_usd)})'
        )

    # ----- SUPPLY ------

    SUPPLY_HELPER_TRANSLATOR = {
        ThorRealms.RESERVES: 'Резервы',
        ThorRealms.STANDBY_RESERVES: 'Неразвернутые резервы',
    }

    def text_metrics_supply(self, market_info: RuneMarketInfo):
        sp = market_info.supply_info

        burn_amt = short_rune(abs(sp.total_burned_rune))
        burn_pct = format_percent(abs(sp.total_burned_rune), sp.total)

        return (
            f'⚡️ Предложение монеты Rune – {pre(pretty_rune(market_info.total_supply))}\n'
            f'🔥 Сожжено Rune – {code(burn_amt)} ({burn_pct}).\n'
            f'🏊‍ Пулы ликвидности: {pre(short_rune(sp.pooled))} ({format_percent(sp.pooled_percent)}).\n'
            f'🏊‍ RUNEPool: {pre(short_rune(sp.runepool))} ({format_percent(sp.runepool_percent)}).\n'
            f'⚡️ POL: {pre(short_rune(sp.pol))} ({format_percent(sp.pol_percent)}).\n'
            f'🔒 Бонды нод: {pre(short_rune(sp.bonded))} ({format_percent(sp.bonded_percent)}).\n'
            f'🏦 Биржи: {pre(short_rune(sp.in_cex))} ({format_percent(sp.in_cex_percent)}).\n'
            f'💰 Сокровищница имеет {pre(short_rune(sp.treasury))}.'
        )

    SUPPLY_PIC_CIRCULATING = 'Прочие циркулирующие'
    SUPPLY_PIC_TEAM = 'Команда'
    SUPPLY_PIC_SEED = 'Сид-инвесторы'
    SUPPLY_PIC_VESTING_9R = 'NineRealms вестинг'
    SUPPLY_PIC_RESERVES = 'Резерв'
    SUPPLY_PIC_UNDEPLOYED = 'Неразвернутый резерв'
    SUPPLY_PIC_BONDED = 'Активный бонд нод'
    SUPPLY_PIC_TREASURY = 'Сокровищница'
    SUPPLY_PIC_MAYA = 'Maya пул'
    SUPPLY_PIC_POOLED = 'В пулах'
    SUPPLY_PIC_BURNED = 'Сожжено'
    SUPPLY_PIC_SECTION_CIRCULATING = 'Нативные циркулируют'
    SUPPLY_PIC_SECTION_LOCKED = 'Нативные заблокированы'
    SUPPLY_PIC_SECTION_KILLED = 'Уничтоженные'

    # ---- MY WALLET ALERTS ----

    TX_COMMENT_TABLE = {
        'Deposit': 'Депозит',
        'Send': 'Перевод',
        'Outbound': 'Исходящая',
        'OutboundTx': 'Исходящая',
    }

    def notification_text_rune_transfer(self, t: NativeTokenTransfer, my_addresses, name_map):
        asset, comment, from_my, to_my, tx_link, usd_amt, memo = self._native_transfer_prepare_stuff(
            my_addresses, t,
            name_map=name_map
        )
        comment = self.TX_COMMENT_TABLE.get(comment, comment)

        return (
            f'🏦 <b>{comment}</b>: {code(short_money(t.amount, postfix=" " + asset))} {usd_amt} '
            f'от {from_my} '
            f'➡️ к {to_my}{memo}.\n'
            f'{tx_link}'
        )

    def notification_text_rune_transfer_public(self, t: NativeTokenTransfer, name_map):
        asset, comment, from_my, to_my, tx_link, usd_amt, memo = self._native_transfer_prepare_stuff(
            None, t,
            name_map=name_map
        )

        return (
            f'💸 <b>Большой перевод</b> {comment}: '
            f'{code(short_money(t.amount, postfix=" " + asset))}{usd_amt} '
            f'от {from_my} ➡️ к {to_my}{memo}.\n'
            f'Транзакция: {tx_link}'
        )

    @staticmethod
    def unsubscribe_text(unsub_id):
        return f'🔕 Отписка: /unsub_{unsub_id}'

    def notification_text_regular_lp_report(self, user, address, pool, lp_report: LiquidityPoolReport, local_name: str,
                                            unsub_id):
        explorer_link, name_str, pretty_pool, thor_yield_link = self._regular_report_variables(address, local_name,
                                                                                               pool)

        return (
            f'Ваш регулярный отчет о позиции ликвидности на адресе {explorer_link}{name_str} в пуле {pre(pretty_pool)} готов.\n'
            f'{thor_yield_link}.\n\n'
            f'{self.unsubscribe_text(unsub_id)}'
        )

    # ------ DEX -------

    @staticmethod
    def format_dex_entry(e: DexReportEntry, r):
        n = e.count
        txs = 'шт.'
        return (
            f'{bold(n)} {txs} '
            f'({pre(short_rune(e.rune_volume))} или '
            f'{pre(short_dollar(e.rune_volume * r.usd_per_rune))})')

    STR_24_HOUR = '24 часа'

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
            f'🤹🏻‍♂️ <b>DEX использование последние {period_str}</b>\n\n'
            f'→ Обмен внутрь: {self.format_dex_entry(r.swap_ins, r)}\n'
            f'← Обмен наружу: {self.format_dex_entry(r.swap_outs, r)}\n'
            f'∑ В сумме: {self.format_dex_entry(r.total, r)}\n\n'
            f'Популярные агрегаторы:\n{top_aggr_str}\n'
            f'Популярные активы:\n{top_asset_str}'
        ).strip()

    @staticmethod
    def pretty_asset(name, abbr=True):
        return BaseLocalization.pretty_asset(name, abbr).replace('synth', 'синт.').replace('trade', 'торг.')

    # ------- RUNEPOOL -------

    def notification_runepool_action(self, event: AlertRunePoolAction, name_map: NameMap):
        if event.is_deposit:
            action_str = 'добавление'
            from_link = self.link_to_address(event.actor, name_map)
            route = f"{from_link} ➡️ RUNEPool"
        else:
            action_str = 'вывод'
            to_link = self.link_to_address(event.destination_address, name_map)
            route = f"RUNEPool ➡️ {to_link}"

        if event.affiliate:
            aff_collector = self.name_service.get_affiliate_name(event.affiliate)
            aff_collector = f'{aff_collector} ' if aff_collector else ''

            aff_text = f'{aff_collector}партнерская комиссия: {format_percent(event.affiliate_rate, 1)}\n'
        else:
            aff_text = ''

        amt_str = f"{pre(pretty_rune(event.amount))}"

        return (
            f"🏦 <b>RUNEPool {action_str}</b>\n"
            f"{route}\n"
            f"Всего: {amt_str} ({pretty_dollar(event.usd_amount)})\n"
            f"{aff_text}"
            f"{self.link_to_tx(event.tx_hash)}\n"
        )

    def notification_runepool_stats(self, event: AlertRunepoolStats):
        n_providers_delta, pnl_delta, rune_delta, share_delta = self._runepool_deltas(event)

        return (
            f'🏦 <b>RUNEPool статистика</b>\n\n'
            f'Всего внесено: {bold(pretty_rune(event.current.rune_value))} {rune_delta}\n'
            f'Доля провайдеров: {bold(pretty_percent(event.current.providers_share, signed=False))} {share_delta}\n'
            f'Доход/убыток: {bold(pretty_rune(event.current.pnl))} {pnl_delta}\n'
            f'Провайдеры Rune: {bold(short_money(event.current.n_providers, integer=True))} {n_providers_delta}\n'
            f'Средний депозит провайдера: {bold(pretty_rune(event.current.avg_deposit))}\n'
        )

    def notification_text_pol_stats(self, event: AlertPOLState):
        text = '🥃 <b>POL: ликвидность протокола</b>\n\n'

        curr, prev = event.current, event.previous
        pol_progress = progressbar(curr.rune_value, event.mimir_max_deposit, 10)

        str_value_delta_pct, str_value_delta_abs = '', ''
        if prev:
            str_value_delta_pct = up_down_arrow(prev.rune_value, curr.rune_value, percent_delta=True, brackets=True)

        pnl_pct = curr.pnl_percent
        text += (
            f"Текущая POL ликвидность: {code(short_rune(curr.rune_value))} или "
            f" {code(short_dollar(curr.usd_value))} {str_value_delta_pct}\n"
            f"Использование: {pre(pretty_percent(event.pol_utilization, signed=False))} {pre(pol_progress)} "
            f" из {short_rune(event.mimir_max_deposit)} максимум.\n"
            f"Rune депонировано: {pre(short_rune(curr.rune_deposited))} "
            f"и выведено: {pre(short_rune(curr.rune_withdrawn))}\n"
            f"Доходы/убытки: {pre(pretty_percent(pnl_pct))} {chart_emoji(pnl_pct)}"
        )

        # POL pool membership
        if event.membership:
            text += "\n\n<b>Членство в пулах:</b>\n"
            text += self._format_pol_membership(event, of_pool='от пула')

        return text.strip()

    # ------ Network identifiers ------

    @staticmethod
    def notification_text_chain_id_changed(event: AlertChainIdChange):
        return (
            f'🆔 <b>Изменение идентификатора цепочки ChainID</b>\n\n'
            f'Старый: {code(event.prev_chain_id)}\n'
            f'Новый: {code(event.curr_chain_id)}\n'
        )

    # ------- Rune burn -------

    @staticmethod
    def notification_rune_burn(e: EventRuneBurn):
        return (
            f'Сегодня сожжено {bold(pretty_rune(e.last_24h_burned_rune))} RUNE '
            f'({bold(pretty_dollar(e.last_24h_burned_usd))})'
        )

    TEXT_SECURED_ASSETS_NO_DATA = '😩 Пока нет данных о секьюред активах.'

    @staticmethod
    def notification_rujira_merge_stats(e: AlertRujiraMergeStats):
        return f'RUJIRA Статистика слияния'

    @staticmethod
    def notification_text_secured_asset_summary(e: AlertSecuredAssetSummary):
        return 'Сводка Secured активов'

    @staticmethod
    def notification_text_tcy_info_caption(e: TcyFullInfo):
        return 'Сводка по TCY'

    # ------ Bond providers alerts ------

    TEXT_BOND_PROVIDER_ALERT_FOR = 'Оповещение для поставщика бонда'
    TEXT_BP_NODE = '⛈️ Нода'

    def bp_event_duration(self, ev: EventProviderStatus):
        dur = ev.duration
        return f' ({self.seconds_human(dur)} с последнего статуса)' if dur else ''

    def bond_provider_event_text(self, event: NodeEvent):
        if event.type == NodeEventType.FEE_CHANGE:
            up = event.data.previous < event.data.current
            verb = 'поднял' if up else 'опустил'
            emoji = '📈' if up else '📉'
            return (
                f'％{emoji} Оператор ноды {ital(verb)} комиссию с '
                f'{pre(format_percent(event.data.previous, 1))} до {pre(format_percent(event.data.current, 1))}.'
            )
        elif event.type == NodeEventType.CHURNING:
            data: EventProviderStatus = event.data
            emoji = '✳️' if data.appeared else '⏳'
            adjective = 'активна' if data.appeared else 'неактивной'
            return f'{emoji} Нода стала {bold(adjective)}. {self.bp_event_duration(data)}'
        elif event.type == NodeEventType.PRESENCE:
            data: EventProviderStatus = event.data
            verb = 'подключилась к сети' if data.appeared else 'отключилась от сети'
            emoji = '✅' if data.appeared else '❌'
            return f'{emoji} Нода {ital(verb)}. {self.bp_event_duration(data)}'
        elif event.type == NodeEventType.BOND_CHANGE:
            data: EventProviderBondChange = event.data
            delta = data.curr_bond - data.prev_bond
            delta_str = up_down_arrow(data.prev_bond, data.curr_bond, money_delta=True, postfix=RAIDO_GLYPH)
            verb = 'вырос' if delta > 0 else 'упал'
            emoji = '📈' if delta > 0 else '📉'
            usd_val = delta * event.usd_per_rune
            apy_str = f' | APY: {bold(format_percent(data.apy, signed=True))}' if data.apy else ''
            duration_str = f" Прошло с последнего изменения: {self.seconds_human(data.duration_sec)}" if data.duration_sec else ''
            return (
                f'{emoji} Размер бонда в ноде {bold(verb)} '
                f'с {pre(pretty_rune(data.prev_bond))} '
                f'до {pre(pretty_rune(data.curr_bond))} '
                f'({ital(delta_str)} | {ital(self.bp_bond_percent(data))} | {short_dollar(usd_val)}{apy_str}).'
                f'{duration_str}'
            )
        elif event.type == NodeEventType.BP_PRESENCE:
            data: EventProviderStatus = event.data
            verb = 'появился в списке' if data.appeared else 'исчез из списка'
            emoji = '🤍' if data.appeared else '📤'
            return f'{emoji} Этот адрес {verb} провайдеров бонда для ноды. {self.bp_event_duration(data)}'
        else:
            return ''

    def text_bond_provision(self, bonds: List[Tuple[NodeInfo, BondProvider]], usd_per_rune: float, name_map=None):
        if not bonds:
            return ''

        message = ''

        bonds.sort(key=(lambda _bp: _bp[1].rune_bond), reverse=True)

        for i, (node, bp) in enumerate(bonds, start=1):
            node_op_text = ' [Оператор]' if bp.is_node_operator else ''
            emoji = '🌩️' if node.is_active else '⏱️'
            node_link = f'{emoji} нода {self.link_to_address(node.node_address, name_map)}'

            if bp.rune_bond > 0:
                if bp.bond_share > 0.1:
                    share_str = f' | {pretty_percent(bp.bond_share * 100.0, signed=False)}'
                else:
                    share_str = ''
                provided_str = (
                    f'{bold(pretty_rune(bp.rune_bond))} '
                    f'({ital(short_dollar(bp.rune_bond * usd_per_rune))}) бонд'
                    f'{share_str}'
                )
            else:
                provided_str = 'нет бонда'
                if not bp.is_node_operator:
                    provided_str += ', но в белом списке'

            if bp.anticipated_award > 0:
                award_text = (
                    f'следующая награда 💰{bold(pretty_rune(bp.anticipated_award))} '
                    f'({ital(short_dollar(bp.anticipated_award * usd_per_rune))})'
                )
            else:
                award_text = 'нет награды'

            message += (
                f'└ {i}. {node_link} ← {provided_str}, '
                f'{award_text}{node_op_text}\n'
            )

        return f'\n\n🔗Предоставление бонда:\n{message}' if message else ''

    @staticmethod
    def notification_text_app_layer_stats(e: WasmPeriodStats):
        calls_delta = up_down_arrow(e.prev_total_calls, e.total_calls, percent_delta=True, brackets=True)
        users_delta = up_down_arrow(e.prev_unique_users, e.unique_users, int_delta=True, brackets=True)
        return (
            f'🤖 <b>Статистика App Layer THORChain</b> ({int(e.days)}д)\n'
            f'📲 {bold(pretty_money(e.total_calls, integer=True))} вызовов {calls_delta}\n'
            f'👥 {bold(pretty_money(e.unique_users, integer=True))} пользователей {users_delta}'
        )

