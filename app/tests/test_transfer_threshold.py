from types import SimpleNamespace

import pytest

from lib.config import SubConfig
from lib.delegates import INotified
from models.pool_info import PoolInfo
from models.transfer import NativeTokenTransfer
from notify.personal.balance import PersonalBalanceNotifier
from notify.public.transfer_notify import RuneMoveNotifier
from tests.fakes import FakeDB, FakePoolCache, make_price_holder

MIN_USD = 900_000  # as on prod


def _price_holder():
    # a RUNE is $2, a BTC is $30 000; TCY and RUJI cost 0.1 RUNE = $0.2, like on the mainnet
    ph = make_price_holder()
    for pool in ('THOR.TCY', 'THOR.RUJI'):
        ph.pool_info_map[pool] = PoolInfo(pool, balance_asset=1_000 * 10 ** 8, balance_rune=100 * 10 ** 8,
                                          pool_units=1, status=PoolInfo.AVAILABLE)
    return ph


class Collector(INotified):
    def __init__(self):
        self.transfers = []

    async def on_data(self, sender, data):
        self.transfers.append(data)


class NoArbBots:
    async def try_to_detect_arb_bot(self, _address):
        return None

    async def is_marked_as_arb(self, _address):
        return False


def _notifier():
    cfg = SimpleNamespace(
        get=lambda _key: SubConfig({
            'cooldown': '1s', 'min_usd': {'native': MIN_USD}, 'cex_list': [], 'hide_arbitrage_bots': False,
        }),
        as_int=lambda _key, default=None: default,  # for ArbBotDetector
    )
    notifier = RuneMoveNotifier(SimpleNamespace(cfg=cfg, db=FakeDB(), pool_cache=FakePoolCache(_price_holder()),
                                                flagship=None))
    notifier.arb_detector = NoArbBots()
    collector = Collector()
    notifier.add_subscriber(collector)
    return notifier, collector


def _transfer(asset, amount):
    return NativeTokenTransfer(from_addr='thor1from', to_addr='thor1to', block=1, tx_hash='TX', amount=amount,
                               asset=asset)


@pytest.mark.asyncio
@pytest.mark.parametrize('asset, amount, is_large', [
    ('rune', 450_001, True),  # $900 002
    ('rune', 449_000, False),  # $898 000
    ('tcy', 1_200_000, False),  # $240 000; priced as RUNE it was $2.4M
    ('x/ruji', 5_000_000, True),  # $1M
    ('btc-btc', 31, True),  # secured BTC, $930 000; priced as RUNE it was $62
    ('x/unknown', 10_000_000, False),  # no pool, no price
])
async def test_threshold_uses_the_token_price(asset, amount, is_large):
    notifier, collector = _notifier()
    await notifier.on_data(None, [_transfer(asset, amount)])
    assert bool(collector.transfers) is is_large


def test_balance_alerts_price_native_tokens():
    transfers = [_transfer(asset, 1.0) for asset in ('rune', 'tcy', 'x/ruji', 'btc-btc', 'x/unknown')]
    PersonalBalanceNotifier._fill_asset_price(transfers, _price_holder())
    assert [t.usd_per_asset for t in transfers] == pytest.approx([2.0, 0.2, 0.2, 30_000.0, 0.0])
