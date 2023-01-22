from localization.achievements.ach_eng import AchievementsEnglishLocalization
from localization.achievements.common import A, ADesc, POSTFIX_RUNE, META_KEY_SPEC
from services.jobs.achievements import Achievement
from services.lib.texts import code, pre


class AchievementsRussianLocalization(AchievementsEnglishLocalization):
    ACHIEVEMENT_DESC_LIST = [
        ADesc(A.TEST, 'Тест метрика'),
        ADesc(A.TEST_SPEC, 'Тест метрика', postfix=POSTFIX_RUNE),

        ADesc(A.DAU, 'Активных пользователей ежедневно'),
        ADesc(A.MAU, 'Активных пользователей ежемесячно'),
        ADesc(A.WALLET_COUNT, 'Количество кошельков'),
        ADesc(A.SWAP_COUNT_TOTAL, 'Общее количество свопов'),
        ADesc(A.SWAP_COUNT_24H, 'Количество свопов за 24 часа'),
        ADesc(A.SWAP_COUNT_30D, 'Количество свопов за 30 дней'),
        ADesc(A.SWAP_UNIQUE_COUNT, 'Уникальных своперов'),
        ADesc(A.ADD_LIQUIDITY_COUNT_TOTAL, 'Общее количество добавлений ликвидности'),
        ADesc(A.ADD_LIQUIDITY_VOLUME_TOTAL, 'Общий объем добавленной ликвидности'),
        ADesc(A.DAILY_VOLUME, 'Ежедневный объем', prefix='$'),
        ADesc(A.ILP_PAID_TOTAL, 'Всего страховки выплачено', postfix=POSTFIX_RUNE),
        ADesc(A.TOTAL_ACTIVE_BOND, 'Всего активный бонд'),
        ADesc(A.TOTAL_BOND, 'Всего в бондах нод', postfix=POSTFIX_RUNE),
        ADesc(A.NODE_COUNT, 'Всего нод в сети', postfix=POSTFIX_RUNE),
        ADesc(A.ACTIVE_NODE_COUNT, 'Число активных нод'),

        ADesc(A.ANNIVERSARY, 'День Рождения'),
        ADesc(A.BLOCK_NUMBER, 'Сгенерировано блоков'),
        ADesc(A.DAILY_TX_COUNT, 'Количество транзакций за день'),
        ADesc(A.TOTAL_MIMIR_VOTES, 'Всего голосов за Mimir'),
        ADesc(A.MARKET_CAP_USD, 'Rune общая капитализации', prefix='$'),
        ADesc(A.TOTAL_POOLS, 'Всего пулов'),
        ADesc(A.TOTAL_ACTIVE_POOLS, 'Активных пулов'),

        ADesc(A.TOTAL_UNIQUE_SAVERS, 'Всего уникальных сберегателей'),
        ADesc(A.TOTAL_SAVED_USD, 'Всего в сберегательных хранилищах', prefix='$'),
        ADesc(A.TOTAL_SAVERS_EARNED_USD, 'Всего заработано на сбережениях', prefix='$'),

        ADesc(A.SAVER_VAULT_SAVED_ASSET, 'Глубина хранилища ::asset::'),
        ADesc(A.SAVER_VAULT_SAVED_USD, 'Глубина хранилища ::asset:: в USD', prefix='$'),
        ADesc(A.SAVER_VAULT_MEMBERS, 'Сберегателей ::asset::'),
        ADesc(A.SAVER_VAULT_EARNED_ASSET, 'Сберегатели заработали ::asset::'),
    ]

    def notification_achievement_unlocked(self, a: Achievement):
        desc, ago, desc_str, emoji, milestone_str, prev_milestone_str, value_str = self.prepare_achievement_data(a)

        msg = f'{emoji} <b>THORChain совершил новое достижение!</b>\n'
        if a.key == a.ANNIVERSARY:
            # special case for anniversary
            years_str = self._years_string(a.milestone)
            msg += f"С Днем рождения! Уже {a.milestone} {years_str} с первого блока!"
        else:
            # default case
            if value_str:
                value_str = f' ({pre(value_str)})'
            msg += f'{pre(desc_str)} теперь больше, чем {code(milestone_str)}{value_str}!'
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
