from abc import ABC, abstractmethod

from aiogram.types import *

from services.lib.money import format_percent, asset_name_cut_chain
from services.lib.utils import progressbar
from services.models.cap_info import ThorInfo
from services.models.pool_info import PoolInfo
from services.models.price import RuneFairPrice, PriceReport, PriceATH
from services.models.tx import StakeTx, StakePoolStats

RAIDO_GLYPH = 'ᚱ'
CREATOR_TG = '@account1242'


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

    START_ME = 'https://telegram.me/thorchain_monitoring_bot?start=1'

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

    BUTTON_SM_ADD_ADDRESS = 'Add an address'
    BUTTON_BACK = 'Back'
    BUTTON_SM_BACK_TO_LIST = 'Back to list'

    BUTTON_SM_BACK_MM = 'Main menu'

    BUTTON_VIEW_RUNESTAKEINFO = 'View it on runestake.info'
    BUTTON_VIEW_VALUE_ON = 'Show value: ON'
    BUTTON_VIEW_VALUE_OFF = 'Show value: OFF'
    BUTTON_REMOVE_THIS_ADDRESS = 'Remove this address'

    TEXT_NO_ADDRESSES = "You have not added any addresses yet. Send me one."
    TEXT_YOUR_ADDRESSES = 'Your addresses:'
    TEXT_INVALID_ADDRESS = 'Invalid address!'
    TEXT_SELECT_ADDRESS_ABOVE = 'Select one from above. ☝️ '
    TEXT_SELECT_ADDRESS_SEND_ME = 'If you want to add one more, please send me it. 👇'
    TEXT_LP_NO_POOLS_FOR_THIS_ADDRESS = ''
    TEXT_LP_IMG_CAPTION = ''

    LP_PIC_POOL = 'POOL'
    LP_PIC_RUNE = 'RUNE'
    LP_PIC_ADDED = 'Added'
    LP_PIC_WITHDRAWN = 'Withdrawn'
    LP_PIC_REDEEM = 'Redeemable'
    LP_PIC_GAIN_LOSS = 'Gain / Loss'
    LP_PIC_IN_USD = 'in USD'
    LP_PIC_R_RUNE = f'{RAIDO_GLYPH}une'
    LP_PIC_ADDED_VALUE = 'Added value'
    LP_PIC_WITHDRAWN_VALUE = 'Withdrawn value'
    LP_PIC_CURRENT_VALUE = 'Current value'
    LP_PIC_PRICE_CHANGE = 'Price change'
    LP_PIC_PRICE_CHANGE_2 = 'since the first addition'
    LP_PIC_LP_VS_HOLD = 'LP vs HOLD'
    LP_PIC_LP_APY = 'LP APY'
    LP_PIC_EARLY = 'Early...'
    LP_PIC_FOOTER = "Powered by Bigboss' runestake.info"

    @abstractmethod
    def pic_stake_days(self, total_days, first_stake_ts):
        ...

    @abstractmethod
    def text_stake_loading_pools(self, address):
        ...

    @abstractmethod
    def text_stake_provides_liq_to_pools(self, address, pools):
        ...

    @abstractmethod
    def text_stake_today(self):
        ...

    # ------- CAP -------

    @abstractmethod
    def notification_text_cap_change(self, old: ThorInfo, new: ThorInfo): ...

    @abstractmethod
    def price_message(self, info: ThorInfo, fair_price: RuneFairPrice): ...

    # ------- NOTIFY STAKES -------

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
    def notification_text_price_update(self, p: PriceReport, ath=False): ...

    # ------- POOL CHURN -------

    @staticmethod
    def pool_link(pool_name):
        return f'https://chaosnet.bepswap.com/pool/{asset_name_cut_chain(pool_name)}'

    @abstractmethod
    def notification_text_pool_churn(self, added_pools, removed_pools, changed_status_pools): ...
