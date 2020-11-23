from services.dialog.main_menu import MainMenuDialog
from services.dialog.stake_info import StakeDialog
from services.lib.depcont import DepContainer


def init_dialogs(d: DepContainer):
    MainMenuDialog.register(d)
    StakeDialog.back_dialog = MainMenuDialog
    StakeDialog.back_func = MainMenuDialog.entry_point
    StakeDialog.register(d)
