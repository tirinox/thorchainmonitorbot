from abc import ABC, abstractmethod

from aiogram.types import *

from services.lib.money import format_percent, asset_name_cut_chain
from services.lib.utils import progressbar
from services.models.cap_info import ThorInfo
from services.models.pool_info import PoolInfo
from services.models.price import RuneFairPrice, PriceReport, PriceATH
from services.models.tx import StakeTx, StakePoolStats


def kbd(buttons, resize=True, vert=False, one_time=False, inline=False, row_width=3):
    if isinstance(buttons, str):
        buttons = [[buttons]]
    elif isinstance(buttons, (list, tuple, set)):
        if all(isinstance(b, str) for b in buttons):
            if vert:
                buttons = [[b] for b in buttons]
            else:
                buttons = [buttons]

    buttons = [
        [KeyboardButton(b) for b in row] for row in buttons
    ]
    return ReplyKeyboardMarkup(buttons,
                               resize_keyboard=resize,
                               one_time_keyboard=one_time,
                               row_width=row_width)


class BaseLocalization(ABC):
    # ----- WELCOME ------

    @staticmethod
    def _cap_progress_bar(info: ThorInfo):
        return f'{progressbar(info.stacked, info.cap, 10)} ({format_percent(info.stacked, info.cap)})\n'

    @abstractmethod
    def help_message(self): ...

    @abstractmethod
    def welcome_message(self, info: ThorInfo): ...

    BUTTON_RUS = 'Русский'
    BUTTON_ENG = 'English'

    THORCHAIN_LINK = 'https://thorchain.org/'

    R = 'Rune'

    def lang_help(self):
        return (
            f'Пожалуйста, выберите язык / Please select a language',
            kbd([self.BUTTON_RUS, self.BUTTON_ENG], one_time=True)
        )

    @abstractmethod
    def unknown_command(self): ...

    BUTTON_MM_MY_ADDRESS = ''
    BUTTON_MM_CAP = ''
    BUTTON_MM_PRICE = ''

    @abstractmethod
    def kbd_main_menu(self): ...

    # ------- STAKE INFO MENU -------

    BUTTON_SM_ADD_ADDRESS = ''

    # ------- CAP -------

    @abstractmethod
    def notification_text_cap_change(self, old: ThorInfo, new: ThorInfo): ...

    @abstractmethod
    def price_message(self, info: ThorInfo, fair_price: RuneFairPrice): ...

    # ------- STAKES -------

    @staticmethod
    def thor_explore_address(address):
        return f'https://viewblock.io/thorchain/address/{address}'

    @staticmethod
    def binance_explore_address(address):
        return f'https://explorer.binance.org/address/{address}'

    @abstractmethod
    def notification_text_large_tx(self,
                                   tx: StakeTx,
                                   dollar_per_rune: float,
                                   pool: StakePoolStats,
                                   pool_info: PoolInfo): ...

    # ------- QUEUE -------

    @abstractmethod
    def notification_text_queue_update(self, item_type, step, value): ...

    # ------- PRICE -------

    DET_PRICE_HELP_PAGE = 'https://docs.thorchain.org/how-it-works/incentive-pendulum'

    @abstractmethod
    def notification_text_price_update(self, p: PriceReport, ath=False, last_ath: PriceATH = None): ...

    # ------- POOL CHURN -------

    @staticmethod
    def pool_link(pool_name):
        return f'https://chaosnet.bepswap.com/pool/{asset_name_cut_chain(pool_name)}'

    @abstractmethod
    def notification_text_pool_churn(self, added_pools, removed_pools, changed_status_pools): ...
