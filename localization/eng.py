from localization.base import BaseLocalization
from services.models.model import ThorInfo


class EnglishLocalization(BaseLocalization):
    def notification_cap_change_text(self, old: ThorInfo, new: ThorInfo):
        verb = "has been increased" if old.cap < new.cap else "has been decreased"
        call = "Come on, go staking!\n" if new.cap > old.cap else ''
        message = f'<b>Cap {verb} from {old.cap:.0f} to {new.cap:.0f}!</b>\n' \
                  f'Currently <b>{new.stacked:.0f}</b> $RUNE are staked.\n' \
                  f'The price of $RUNE in the pool is <code>{new.price:.3f} BUSD</code>.\n' \
                  f'{call}' \
                  f'https://chaosnet.bepswap.com/'
        return message

    def welcome_message(self, info: ThorInfo):
        return f"Hello! <b>{info.stacked:.0f}</b> coins of <b>{info.cap:.0f}</b> are currently staked.\n" \
               f"The $RUNE price is <code>{info.price:.3f} BUSD</code> now."

    def price_message(self, info: ThorInfo):
        return f"Last $RUNE price: <code>{info.price:.3f} BUSD</code>."
