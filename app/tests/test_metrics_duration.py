import pytest

from comm.dialog.metrics_menu import MetricsDialog
from comm.localization.eng_base import EnglishLocalization
from comm.localization.rus import RussianLocalization
from lib.config import Config
from lib.date_utils import HOUR, DAY


class FakeMessage:
    def __init__(self, text):
        self.text = text
        self.replies = []

    async def reply(self, text, **_kwargs):
        self.replies.append(text)


def _dialog(loc_class):
    # skip __init__: it needs the bot, the FSM storage and the deps
    dialog = MetricsDialog.__new__(MetricsDialog)
    dialog.loc = loc_class(Config(name='./tests/test_config.yaml'))
    dialog.data = {dialog.KEY_NEXT_ACTION: 'price', dialog.KEY_BACK_SUBMENU: 'financial'}
    dialog.shown = []

    async def show_price(_message, period):
        dialog.shown.append(('price', period))

    async def show_menu_financial(_message):
        dialog.shown.append(('back', None))

    dialog.show_price = show_price
    dialog.show_menu_financial = show_menu_financial
    return dialog


@pytest.mark.asyncio
@pytest.mark.parametrize('loc_class', [EnglishLocalization, RussianLocalization])
@pytest.mark.parametrize('text', ['5x', '1d 6', 'h', 'week'])
async def test_invalid_period_gets_an_answer(loc_class, text):
    dialog = _dialog(loc_class)
    message = FakeMessage(text)

    await dialog.on_generic_duration_reply(message)

    assert message.replies == [dialog.loc.TEXT_INVALID_DURATION]
    assert dialog.shown == []


@pytest.mark.asyncio
@pytest.mark.parametrize('text, period', [('12h', 12 * HOUR), ('1d 6h', DAY + 6 * HOUR), ('90', 90)])
async def test_typed_period(text, period):
    dialog = _dialog(EnglishLocalization)
    await dialog.on_generic_duration_reply(FakeMessage(text))
    assert dialog.shown == [('price', period)]


@pytest.mark.asyncio
async def test_buttons():
    dialog = _dialog(EnglishLocalization)
    await dialog.on_generic_duration_reply(FakeMessage(dialog.loc.BUTTON_24_HOURS))
    await dialog.on_generic_duration_reply(FakeMessage(dialog.loc.BUTTON_BACK))
    assert dialog.shown == [('price', DAY), ('back', None)]
