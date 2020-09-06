from broadcast import broadcaster
from config import DB
from fetcher import ThorInfo
from aiogram.types import *


BUTTON_GET_UPDATE = 'Получить обновление!'


def make_text_for_cap_change(old: ThorInfo, new: ThorInfo):
    verb = "подрос" if old.cap < new.cap else "упал"
    message = f'<b>Кап {verb} с {old.cap:.0f} до {new.cap:.0f}!</b>\n' \
              f'Сейчас застейкано <b>{new.stacked:.0f}</b> $RUNE.\n' \
              f'Цена $RUNE в пуле <code>{new.price:.3f} BUSD</code>.\n' \
              f'Ай-да застейкаем!\n' \
              f'https://chaosnet.bepswap.com/'
    return message


async def welcome_message(db: DB):
    info = await db.get_old_cap()
    return f"Привет! <b>{info.stacked:.0f}</b> монет из <b>{info.cap:.0f}</b> сейчас застейканы.\n" \
           f"Цена $RUNE сейчас <code>{info.price:.3f} BUSD</code>."


async def notify_when_cap_changed(bot, db: DB, old: ThorInfo, new: ThorInfo, is_ath):
    users = await db.all_users()
    message = make_text_for_cap_change(old, new)
    _, _, bad_ones = await broadcaster(bot, users, message)
    await db.remove_users(bad_ones)


async def price_message(db: DB):
    info = await db.get_old_cap()
    return f"Последняя цена $RUNE: <code>{info.price:.3f} BUSD</code>."
