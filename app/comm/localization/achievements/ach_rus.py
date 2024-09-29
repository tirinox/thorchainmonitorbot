from jobs.achievement.ach_list import Achievement, A
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
        A.DAILY_VOLUME: "Ежедневный объем",
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
        A.TOTAL_UNIQUE_SAVERS: "Всего уникальных сберегателей",
        A.TOTAL_SAVED_USD: "Всего в сберегательных хранилищах",
        A.TOTAL_SAVERS_EARNED_USD: "Всего заработано на сбережениях",
        A.SAVER_VAULT_SAVED_ASSET: "Глубина хранилища ::asset::",
        A.SAVER_VAULT_SAVED_USD: "Глубина хранилища ::asset:: в USD",
        A.SAVER_VAULT_MEMBERS: "Сберегателей ::asset::",
        A.SAVER_VAULT_EARNED_ASSET: "Сберегатели заработали ::asset::",
        A.SWAP_VOLUME_TOTAL_RUNE: "Общий объем свопов в RUNE",
        A.MAX_SWAP_AMOUNT_USD: "Максимальный объем обмена",
        A.MAX_ADD_AMOUNT_USD: "Максимальный объем добавления",
        A.MAX_ADD_AMOUNT_USD_PER_POOL: "Добавлено ::asset:: в пул за раз",
        A.COIN_MARKET_CAP_RANK: "Место по капитализации",
        A.POL_VALUE_RUNE: "POL вклад в Rune",
        A.BTC_IN_VAULT: "Bitcoin в хранилище",
        A.ETH_IN_VAULT: "Ethereum в хранилище",
        A.STABLES_IN_VAULT: "Стейблы в хранилище",

        A.TOTAL_VALUE_LOCKED: "Всего залочено USD",
        A.WEEKLY_SWAP_VOLUME: "Еженедельный объем свопов",
        A.WEEKLY_PROTOCOL_REVENUE_USD: "Еженедельный доход протокола",
        A.WEEKLY_AFFILIATE_REVENUE_USD: "Еженедельный доход партнеров",

        A.RUNE_BURNT_LENDING: "RUNE сожжено",
        A.LOANS_OPENED: "Открыто займов",
        A.BORROWER_COUNT: "Количество заемщиков",
        A.MAX_LOAN_AMOUNT_USD: "Максимальный размер займа",
        A.TOTAL_BORROWED_USD: "Всего занято средств",
        A.TOTAL_COLLATERAL_USD: "Всего залогов внесено",

        A.TRADE_BALANCE_TOTAL_USD: "Общий баланс торговых счетов",
        A.TRADE_ASSET_HOLDERS_COUNT: "Держателей торговых активов",
        A.TRADE_ASSET_SWAPS_COUNT: "Свопов торговых активов",
        A.TRADE_ASSET_SWAPS_VOLUME: "Объем свопов торговых активов",
        A.TRADE_ASSET_MOVE_COUNT: "Операций торговых счетов",
        A.TRADE_ASSET_LARGEST_DEPOSIT: "Самый крупный депозит",

        A.RUNEPOOL_VALUE_USD: "RUNEPool ценность",
        A.RUNEPOOL_LARGEST_DEPOSIT: "Самый крупный депозит в RUNEPool",
        A.RUNEPOOL_TOTAL_PROVIDERS: "Всего провайдеров в RUNEPool",
        A.RUNEPOOL_PNL: "Прибыль RUNEPool",
    }

    MORE_THAN = 'Более чем'

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
