from aiogram.types import *

from localization.base import BaseLocalization, kbd
from services.lib.datetime import format_time_ago
from services.lib.money import pretty_dollar, pretty_money, short_address, adaptive_round_to_str, calc_percent_change, \
    emoji_for_percent_change
from services.lib.utils import link, code, bold, pre, x_ses, ital
from services.models.cap_info import ThorInfo
from services.models.pool_info import PoolInfo
from services.models.price import RuneFairPrice, PriceReport, PriceATH
from services.models.tx import StakeTx, short_asset_name, StakePoolStats


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
        )

    def welcome_message(self, info: ThorInfo):
        return (
            f"Привет! <b>{info.stacked:.0f}</b> монет из <b>{info.cap:.0f}</b> сейчас застейканы.\n"
            f"{self._cap_progress_bar(info)}"
            f"Цена {self.R} сейчас <code>{info.price:.3f} BUSD</code>.\n"
            f"<b>⚠️ Бот теперь уведомляет только в канале @thorchain_alert!</b>\n"
            f"Набери /help, чтобы видеть список команд."
        )

    def unknown_command(self):
        return (
            "🙄 Извини, я не знаю такой команды.\n"
            "Нажми на /help, чтобы увидеть доступные команды."
        )

    # ----- MAIN MENU ------

    BUTTON_MM_MY_ADDRESS = 'Мои адреса'
    BUTTON_MM_CAP = 'Кап ликвидности'
    BUTTON_MM_PRICE = f'Инфо о цене {BaseLocalization.R}'

    def kbd_main_menu(self):
        return kbd([self.BUTTON_MM_MY_ADDRESS, self.BUTTON_MM_PRICE, self.BUTTON_MM_CAP])

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

        return (
            f"<b>{pretty_money(tx.rune_amount)} {self.R}</b> ({rp:.0f}%) ↔️ "
            f"<b>{pretty_money(tx.asset_amount)} {short_asset_name(tx.pool)}</b> ({ap:.0f}%)\n"
            f"Всего: <code>${pretty_money(total_usd_volume)}</code>\n"
            f"Глубина пула сейчас: <b>${pretty_money(pool_depth_usd)}</b>.\n"
            f"Thor обозреватель: {thor_tx} / Binance обозреватель: {bnb_tx}."
        )

    # ------- QUEUE -------

    def notification_text_queue_update(self, item_type, step, value):
        if step == 0:
            return f"☺️ Очередь {item_type} снова опустела!"
        else:
            return f"🤬 <b>Внимание!</b> Очередь {code(item_type)} имеет {value} транзакций!"

    # ------- PRICE -------

    def notification_text_price_update(self, p: PriceReport, ath=False, last_ath: PriceATH = None):
        title = bold('Обновление цены') if not ath else bold('🚀 Достигнуть новый исторический максимум!')

        c_gecko_url = 'https://www.coingecko.com/ru/' \
                      '%D0%9A%D1%80%D0%B8%D0%BF%D1%82%D0%BE%D0%B2%D0%B0%D0%BB%D1%8E%D1%82%D1%8B/thorchain'
        c_gecko_link = link(c_gecko_url, 'RUNE')

        message = f"{title} | {c_gecko_link}\n\n"
        price = p.fair_price.real_rune_price

        pr_text = f"${price:.2f}"
        message += f"Цена <b>RUNE</b> сейчас {code(pr_text)}.\n"

        if last_ath is not None:
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
