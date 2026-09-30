from datetime import datetime
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest

from api.midgard.name_service import NameMap
from comm.dialog.my_wallets_menu import MyWalletsMenu
from comm.localization.eng_base import EnglishLocalization
from comm.localization.rus import RussianLocalization
from lib.config import Config
from lib.constants import RUNE_DENOM
from lib.emergency import EmergencyReport, ReportedEvent
from models.transfer import NativeTokenTransfer

EVIL = '<a href="https://x.io">CLAIM</a> & <'  # fits the 42-char memo limit


class _Tags(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.hrefs = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.hrefs.append(dict(attrs).get('href'))


def _transfer(memo):
    return NativeTokenTransfer(
        from_addr='thor1from', to_addr='thor1to', block=1, tx_hash='ABCDEF',
        amount=10.0, asset=RUNE_DENOM, memo=memo,
    )


@pytest.mark.parametrize('loc_class', [EnglishLocalization, RussianLocalization])
def test_transfer_memo_is_escaped(loc_class):
    loc = loc_class(Config(name='./tests/test_config.yaml'))
    t = _transfer(EVIL)

    texts = (
        loc.notification_text_rune_transfer(t, ['thor1to'], NameMap.empty()),
        loc.notification_text_rune_transfer_public(t, NameMap.empty()),
    )
    for text in texts:
        assert 'https://x.io' not in _Tags(text).hrefs
        assert '&lt;a href=&quot;https://x.io&quot;&gt;CLAIM&lt;/a&gt; &amp; &lt;' in text

    # a long memo is cut before escaping, so no entity is cut in half
    text = loc.notification_text_rune_transfer(_transfer('<' * 100), ['thor1to'], NameMap.empty())
    assert '&lt;' * 39 + '...' in text


def test_wallet_name_is_escaped_and_cut():
    menu = SimpleNamespace(MAX_NAME_LEN=MyWalletsMenu.MAX_NAME_LEN)

    assert MyWalletsMenu._clean_local_name(menu, '  <b>x</b> & y ') == '&lt;b&gt;x&lt;/b&gt; &amp; y'
    assert len(MyWalletsMenu._clean_local_name(menu, 'n' * 100)) == MyWalletsMenu.MAX_NAME_LEN


class FakeBot:
    def __init__(self):
        self.texts = []

    async def send_message(self, _chat_id, text, **_kwargs):
        self.texts.append(text)


@pytest.mark.asyncio
async def test_emergency_report_is_escaped():
    bot = FakeBot()
    report = EmergencyReport('1', bot)

    await report._process_item(ReportedEvent(
        'scanner', "'<' not supported", datetime(2026, 1, 1), {'url': 'https://x?a=1&b=<2>'},
    ))

    text = bot.texts[0]
    assert '<code>&#x27;&lt;&#x27; not supported</code>' in text
    assert 'a=1&amp;b=&lt;2&gt;' in text
