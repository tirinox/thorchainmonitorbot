from broadcast import broadcaster
from config import DB
from fetcher import ThorInfo
from aiogram.types import *


BUTTON_GET_UPDATE = 'Get an update!'


def make_text_for_cap_change(old: ThorInfo, new: ThorInfo):
    verb = "lifted" if old.cap < new.cap else "dropped"
    message = f'<b>Cap {verb} from {old.cap:.0f} up to {new.cap:.0f}!</b>\n' \
              f'Pool price is <code>{new.price:.2f} BUSD/RUNE</code>.\n' \
              f'Come on!\n' \
              f'https://chaosnet.bepswap.com/stake/BNB'
    return message


async def welcome_message(db: DB):
    info = await db.get_old_cap()
    return f"Hey! <b>{info.stacked:.0f}</b> of <b>{info.cap:.0f}</b> is staked now.\n" \
           f"Pool price is <code>{info.price:.2f} BUSD/RUNE</code>."


async def notify_when_cap_changed(bot, db: DB, old: ThorInfo, new: ThorInfo, is_ath):
    users = await db.all_users()
    message = make_text_for_cap_change(old, new)
    _, _, bad_ones = await broadcaster(bot, users, message)
    await db.remove_users(bad_ones)


def hi_message(info: ThorInfo):
    return f"<b>{info.stacked:.0f}</b> of <b>{info.cap:.0f}</b> is staked now."
