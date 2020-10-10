from localization.base import BaseLocalization, pretty_money, link
from services.models.cap_info import ThorInfo
from services.models.tx import StakeTx, short_asset_name


class RussianLocalization(BaseLocalization):
    # ---- WELCOME ----

    def help(self):
        return f"Этот бот уведомляет о крупных движениях с сети {link('https://thorchain.org/', 'THORChain')}.\n" \
               f"Команды:\n" \
               f"/help – эта помощь\n" \
               f"/start – запуск и установка языка\n" \
               f"/cap – текущий кап для стейка в пулах Chaosnet\n" \
               f"/price – текущая цена Rune.\n" \
               f"<b>Все уведомления в канале @thorchain_alert.</b>"

    def welcome_message(self, info: ThorInfo):
        return f"Привет! <b>{info.stacked:.0f}</b> монет из <b>{info.cap:.0f}</b> сейчас застейканы.\n" \
               f"Цена $RUNE сейчас <code>{info.price:.3f} BUSD</code>.\n" \
               f"Бот теперь уведомляет только в канале: @thorchain_alert"

    # ----- CAP ------
    def notification_cap_change_text(self, old: ThorInfo, new: ThorInfo):
        verb = "подрос" if old.cap < new.cap else "упал"
        call = "Ай-да застейкаем!\n" if new.cap > old.cap else ''
        message = f'<b>Кап {verb} с {old.cap:.0f} до {new.cap:.0f}!</b>\n' \
                  f'Сейчас застейкано <b>{new.stacked:.0f}</b> $RUNE.\n' \
                  f'Цена $RUNE в пуле <code>{new.price:.3f} BUSD</code>.\n' \
                  f'{call}' \
                  f'https://chaosnet.bepswap.com/'
        return message

    # ------ PRICE -------
    def price_message(self, info: ThorInfo):
        return f"Последняя цена $RUNE: <code>{info.price:.3f} BUSD</code>."

    # ------ TXS -------
    def tx_text(self, tx: StakeTx, rune_per_dollar):
        msg = ''
        if tx.type == 'stake':
            msg += f'🐳 <b>Кит застейкал</b> 🟢\n'
        elif tx.type == 'unstake':
            msg += f'🐳 <b>Кит вывел из стейка</b> 🔴\n'

        rp, ap = tx.symmetry_rune_vs_asset()
        msg += f"<b>{pretty_money(tx.rune_amount)} ᚱune</b> ({rp:.0f}%) ↔️ " \
               f"<b>{pretty_money(tx.asset_amount)} {short_asset_name(tx.pool)}</b> ({ap:.0f}%)\n"

        total_usd_volume = tx.full_rune / rune_per_dollar if rune_per_dollar != 0 else 0.0
        msg += f"Всего: <code>${pretty_money(total_usd_volume)}</code>\n"

        rune_stake_info = link(f'https://runestake.info/demo?address={tx.address}', 'RuneStake.info')
        msg += f"Статистика этого адреса: {rune_stake_info}"
        return msg
