import os
from types import SimpleNamespace

import pytest
from PIL import Image

from comm.picture import crypto_logo
from comm.picture.crypto_logo import CryptoLogoDownloader, check_pool_logos, chain_logo_name
from lib.config import Config
from models.asset import Asset
from models.pool_info import PoolInfo
from notify.public.pool_churn_notify import PoolChurnNotifier
from tests.fakes import FakeDB

RUNTIME_CFG = Config(data={'pool_churn': {'notification': {'cooldown': '1h'}}})

BSC_USDC = 'BSC.USDC-0X8AC76A51CC950D9822D68B83FE1AD97B32CD580D'
BASE_USDC = 'BASE.USDC-0X833589FCD6EDB6E08F4C7C32D4F71B54BDA02913'


# ---------------- the badge of the chain ----------------

@pytest.mark.parametrize('asset, logo', [
    (BSC_USDC, 'BSC.BNB'),  # a token is told apart by the gas asset of its chain
    ('ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48', 'ETH.ETH'),
    (BASE_USDC, 'BASE'),
    ('BTC.BTC', ''),  # the asset says it itself
    ('ETH.ETH', ''),
    ('BASE.ETH', ''),
])
def test_chain_logo_name(asset, logo):
    assert chain_logo_name(Asset.from_string(asset)) == logo


# ---------------- one logo ----------------

def write_png(path):
    Image.new('RGBA', (8, 8), (255, 0, 0, 255)).save(path, 'png')


@pytest.fixture
def downloader(tmp_path):
    return CryptoLogoDownloader(str(tmp_path))


def fake_download(monkeypatch, status=200, content=write_png):
    """Replaces the download: it writes the file the way download_file does and answers with the HTTP status"""
    urls = []

    async def download_file(url, target_path):
        urls.append(url)
        if status == 200:
            if content is write_png:
                write_png(target_path)
            else:
                with open(target_path, 'wb') as f:
                    f.write(content)
        return status

    monkeypatch.setattr(crypto_logo, 'download_file', download_file)
    return urls


@pytest.mark.asyncio
async def test_a_logo_that_is_there_is_not_downloaded(monkeypatch, downloader):
    urls = fake_download(monkeypatch, status=500)
    write_png(downloader.path_to_local_coin_image(BSC_USDC))
    assert await downloader.ensure_logo(BSC_USDC) == ''
    assert urls == []


@pytest.mark.asyncio
async def test_a_missing_logo_is_downloaded(monkeypatch, downloader):
    urls = fake_download(monkeypatch)
    assert await downloader.ensure_logo(BSC_USDC) == ''
    assert len(urls) == 1 and 'smartchain/assets/0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d/logo.png' in urls[0]
    Image.open(downloader.path_to_local_coin_image(BSC_USDC)).verify()


@pytest.mark.asyncio
async def test_a_logo_that_cannot_be_downloaded_says_why(monkeypatch, downloader):
    fake_download(monkeypatch, status=404)
    problem = await downloader.ensure_logo(BSC_USDC)
    assert 'HTTP 404' in problem and 'smartchain' in problem
    assert not os.path.exists(downloader.path_to_local_coin_image(BSC_USDC))


@pytest.mark.asyncio
async def test_a_file_that_is_not_a_picture_is_a_problem_and_is_removed(monkeypatch, downloader):
    fake_download(monkeypatch, content=b'<html>Not found</html>')
    assert await downloader.ensure_logo(BSC_USDC)  # a problem
    # or it would be taken for the logo from now on
    assert not os.path.exists(downloader.path_to_local_coin_image(BSC_USDC))


# ---------------- the logos of pools ----------------

class FakeLogos:
    def __init__(self, problems=None):
        self.problems = problems or {}
        self.checked = []

    async def ensure_logo(self, logo):
        self.checked.append(logo)
        return self.problems.get(logo, '')


@pytest.mark.asyncio
async def test_pool_needs_the_logo_of_its_asset_and_of_its_chain_once():
    logos = FakeLogos()
    problems = await check_pool_logos(logos, [BSC_USDC, 'BSC.BTCB-0X7130D2A12B9BCBFAE4F2634D864A1EE1CE3EAD9C',
                                              'BTC.BTC', BASE_USDC])
    assert problems == {}
    # BSC.BNB is the badge of both BSC tokens and is looked at once; BTC.BTC has no badge
    assert logos.checked == [BSC_USDC, 'BSC.BNB', 'BSC.BTCB-0X7130D2A12B9BCBFAE4F2634D864A1EE1CE3EAD9C',
                             'BTC.BTC', BASE_USDC, 'BASE']


@pytest.mark.asyncio
async def test_problems_are_keyed_by_the_file_to_put():
    logos = FakeLogos({BSC_USDC: 'HTTP 404', 'BSC.BNB': 'HTTP 500'})
    problems = await check_pool_logos(logos, [BSC_USDC, 'BTC.BTC'])
    assert problems == {f'{BSC_USDC}.png': 'HTTP 404', 'BSC.BNB.png': 'HTTP 500'}


@pytest.mark.asyncio
async def test_something_that_is_not_a_pool_is_a_problem_too():
    problems = await check_pool_logos(FakeLogos(), [123, 'BTC.BTC'])
    assert list(problems) == ['123'] and 'not an asset' in problems['123']


# ---------------- the notifier ----------------

class FakeEmergency:
    def __init__(self):
        self.reports = []

    def report(self, module, message, /, **kwargs):
        self.reports.append((module, message, kwargs))


def make_notifier(logos):
    emergency = FakeEmergency()
    deps = SimpleNamespace(cfg=RUNTIME_CFG, db=FakeDB(), flagship=None, emergency=emergency)
    notifier = PoolChurnNotifier(deps, logo_downloader=logos)
    sent = []

    class Listener:
        async def on_data(self, sender, data):
            sent.append(data)

    notifier.add_subscriber(Listener())
    return notifier, emergency, sent


class Holder:
    usd_per_rune = 2.0

    def __init__(self, **status_by_name):
        self.pool_info_map = {n: PoolInfo(n, 10 ** 12, 10 ** 12, 1, st) for n, st in status_by_name.items()}


async def churn_once(notifier, before, after):
    await notifier.on_data(None, Holder(**before))  # the first look only remembers
    await notifier.on_data(None, Holder(**after))


@pytest.mark.asyncio
async def test_a_new_pool_with_all_logos_is_quiet():
    logos = FakeLogos()
    notifier, emergency, sent = make_notifier(logos)
    await churn_once(notifier, {'BTC.BTC': 'available'}, {'BTC.BTC': 'available', BSC_USDC: 'staged'})
    assert emergency.reports == []
    assert BSC_USDC in logos.checked and 'BSC.BNB' in logos.checked  # a staged pool is checked when it shows up
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_a_new_pool_without_a_logo_is_reported_and_still_announced():
    logos = FakeLogos({'BSC.BNB': 'HTTP 404 for https://example/logo.png'})
    notifier, emergency, sent = make_notifier(logos)
    await churn_once(notifier, {'BTC.BTC': 'available'}, {'BTC.BTC': 'available', BSC_USDC: 'staged'})

    assert len(emergency.reports) == 1
    module, message, details = emergency.reports[0]
    assert module == 'PoolChurnNotifier'
    assert BSC_USDC in message  # the pool is in the message: the emergency mutes the same message
    assert details['problems'] == {'BSC.BNB.png': 'HTTP 404 for https://example/logo.png'}
    assert len(sent) == 1  # the alert is not lost


@pytest.mark.asyncio
async def test_an_activated_pool_is_checked_too_other_changes_are_not():
    logos = FakeLogos()
    notifier, emergency, _ = make_notifier(logos)
    await churn_once(notifier, {'BTC.BTC': 'available', BSC_USDC: 'staged', 'ETH.ETH': 'available'},
                     {'BTC.BTC': 'available', BSC_USDC: 'available', 'ETH.ETH': 'suspended'})
    assert BSC_USDC in logos.checked
    assert 'ETH.ETH' not in logos.checked and 'BTC.BTC' not in logos.checked


@pytest.mark.asyncio
async def test_a_failing_check_does_not_cost_the_alert():
    class Broken:
        async def ensure_logo(self, logo):
            raise RuntimeError('disk is gone')

    notifier, emergency, sent = make_notifier(Broken())
    await churn_once(notifier, {'BTC.BTC': 'available'}, {'BTC.BTC': 'available', BSC_USDC: 'staged'})
    assert len(sent) == 1
    # a failed check of one logo is a problem like any other: the admin is told
    assert len(emergency.reports) == 1 and 'disk is gone' not in emergency.reports[0][1]


@pytest.mark.asyncio
async def test_no_emergency_in_deps_is_fine():
    notifier, _, sent = make_notifier(FakeLogos({'BSC.BNB': 'HTTP 404'}))
    del notifier.deps.emergency
    await churn_once(notifier, {'BTC.BTC': 'available'}, {'BTC.BTC': 'available', BSC_USDC: 'staged'})
    assert len(sent) == 1
