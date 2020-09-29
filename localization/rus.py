from localization.base import BaseLocalization
from services.fetch.model import ThorInfo


class RussianLocalization(BaseLocalization):
    def notification_cap_change_text(self, old: ThorInfo, new: ThorInfo):
        verb = "подрос" if old.cap < new.cap else "упал"
        call = "Ай-да застейкаем!\n" if new.cap > old.cap else ''
        message = f'<b>Кап {verb} с {old.cap:.0f} до {new.cap:.0f}!</b>\n' \
                  f'Сейчас застейкано <b>{new.stacked:.0f}</b> $RUNE.\n' \
                  f'Цена $RUNE в пуле <code>{new.price:.3f} BUSD</code>.\n' \
                  f'{call}' \
                  f'https://chaosnet.bepswap.com/'
        return message

    def welcome_message(self, info: ThorInfo):
        return f"Привет! <b>{info.stacked:.0f}</b> монет из <b>{info.cap:.0f}</b> сейчас застейканы.\n" \
               f"Цена $RUNE сейчас <code>{info.price:.3f} BUSD</code>."

    def price_message(self, info: ThorInfo):
        return f"Последняя цена $RUNE: <code>{info.price:.3f} BUSD</code>."
