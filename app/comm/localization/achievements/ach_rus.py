from datetime import datetime

from jobs.achievement.ach_list import Achievement, A
from lib.date_utils import seconds_human
from lib.texts import code, pre
from .ach_eng import AchievementsEnglishLocalization


class AchievementsRussianLocalization(AchievementsEnglishLocalization):
    TRANSLATION_MAP = {
        A.TEST: "Тест метрика",
        A.TEST_SPEC: "Тест метрика",
        A.TEST_DESCENDING: "Тест наоборот",
        A.DAU: "Активных пользователей ежедневно",
        A.MAU: "Активных пользователей ежемесячно",
        A.WALLET_COUNT: "Количество кошельков",
        A.SWAP_COUNT_TOTAL: "Общее количество свопов",
        A.SWAP_COUNT_24H: "Количество свопов за 24 часа",
        A.SWAP_COUNT_30D: "Количество свопов за 30 дней",
        A.ADD_LIQUIDITY_COUNT_TOTAL: "Общее количество добавлений ликвидности",
        A.ADD_LIQUIDITY_VOLUME_TOTAL: "Общий объем добавленной ликвидности",
        A.DAILY_VOLUME: "Объем свопов за день",
        A.MONTHLY_SWAP_VOLUME: "Объем свопов за месяц",
        A.TOTAL_ACTIVE_BOND: "Всего активный бонд",
        A.TOTAL_BOND: "Всего в бондах нод",
        A.NODE_COUNT: "Всего нод в сети",
        A.ACTIVE_NODE_COUNT: "Число активных нод",
        A.ANNIVERSARY: "День Рождения",
        A.BLOCK_NUMBER: "Сгенерировано блоков",
        A.DAILY_TX_COUNT: "Количество транзакций за день",
        A.TOTAL_MIMIR_VOTES: "Всего голосов за Mimir",
        A.MARKET_CAP_USD: "Rune общая капитализации",
        A.TOTAL_POOLS: "Всего пулов",
        A.TOTAL_ACTIVE_POOLS: "Активных пулов",
        A.SWAP_VOLUME_TOTAL_USD: "Общий объем свопов",
        A.MAX_SWAP_AMOUNT_USD: "Максимальный объем обмена",
        A.MAX_ADD_AMOUNT_USD: "Максимальный объем добавления",
        A.COIN_MARKET_CAP_RANK: "Место по капитализации",
        A.POL_VALUE_USD: "Стоимость POL",
        A.BTC_IN_VAULT: "Bitcoin в хранилище",
        A.ETH_IN_VAULT: "Ethereum в хранилище",
        A.STABLES_IN_VAULT: "Стейблы в хранилище",

        A.TOTAL_VALUE_LOCKED: "Всего залочено USD",
        A.WEEKLY_SWAP_VOLUME: "Еженедельный объем свопов",
        A.WEEKLY_PROTOCOL_REVENUE_USD: "Еженедельный доход протокола",
        A.WEEKLY_AFFILIATE_REVENUE_USD: "Еженедельный доход партнеров",

        A.TRADE_BALANCE_TOTAL_USD: "Общий баланс торговых счетов",
        A.TRADE_ASSET_HOLDERS_COUNT: "Держателей торговых активов",
        A.TRADE_ASSET_LARGEST_DEPOSIT: "Самый крупный депозит на торговый счёт",
    }

    MORE_THAN = 'Более чем'
    LESS_THAN = 'Менее чем'

    CARD_RANK_LABEL = 'Топ'
    CARD_PREVIOUS = 'Было'
    CARD_NOW = 'Сейчас'
    CARD_NEXT = 'Следующая цель'
    MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
              'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']

    def seconds_human(self, seconds) -> str:
        # imported here: rus.py imports this module
        from comm.localization.rus import RussianLocalization
        return seconds_human(seconds, translate=RussianLocalization.DATE_TRANSLATOR)

    def format_date(self, ts) -> str:
        d = datetime.fromtimestamp(ts)
        return f'{d.day} {self.MONTHS[d.month - 1]} {d.year}'

    def card_ago(self, ago: str) -> str:
        return f'{ago} назад'

    def card_anniversary_subtitle(self, years: int) -> str:
        return f'{years} {self._years_string(years)} с первого блока'

    def notification_achievement_unlocked(self, a: Achievement):
        desc, ago, desc_str, emoji, milestone_str, prev_milestone_str, value_str = self.prepare_achievement_data(a)

        msg = f'{emoji} <b>THORChain достиг нового рубежа!</b>\n'
        if a.key == A.ANNIVERSARY:
            # special case for anniversary
            years_str = self._years_string(a.milestone)
            msg += f"С Днем рождения! Уже {a.milestone} {years_str} с первого блока!"
        elif a.key == A.COIN_MARKET_CAP_RANK:
            msg += f"THORChain Rune заняла <b>#{milestone_str}</b> место по капитализации!"
            if a.has_previous:
                msg += f'\nПредыдущее место: {pre(prev_milestone_str)} ({ago} назад)'
        else:
            # default case
            if value_str:
                value_str = f' ({pre(value_str)})'

            relation_str = 'теперь меньше, чем' if a.descending else 'теперь больше, чем'

            msg += f'{pre(desc_str)} {relation_str} {code(milestone_str)}{value_str}!'
            if a.has_previous:
                msg += f'\nПредыдущая веха: {pre(prev_milestone_str)} ({ago} назад)'

        if desc.url:
            msg += f'\n{desc.url}'

        return msg

    @staticmethod
    def _years_string(years: int) -> str:
        if years == 1:
            return 'год'
        if years < 5:
            return 'года'
        return 'лет'
