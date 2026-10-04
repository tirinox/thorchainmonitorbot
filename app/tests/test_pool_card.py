import json
import os
from types import SimpleNamespace

import pytest

from comm.localization.eng_base import EnglishLocalization
from comm.localization.rus import RussianLocalization
from comm.picture.pool_card import build_pool_activated_card, pool_activated_card_filename, short_contract, \
    POOL_ACTIVATED_TEMPLATE
from lib.config import Config
from models.pool_info import PoolInfo, PoolChange, PoolChanges
from notify.alert_presenter import AlertPresenter
from notify.channel import BoardMessage
from notify.public.pool_churn_notify import PoolChurnNotifier
from tests.fakes import FakeDB

CFG = Config(name='./tests/test_config.yaml')
# the sections of the notifier and of the presenter that the test config does not have
RUNTIME_CFG = Config(data={'pool_churn': {'notification': {'cooldown': '1h'}}, 'infographic_renderer': {}})

BSC_USDC = 'BSC.USDC-0X8AC76A51CC950D9822D68B83FE1AD97B32CD580D'


def make_pools(**status_by_name):
    """name => PoolInfo with 1M RUNE and 1M of the asset"""
    return {name: PoolInfo(name, 100_000_000_000_000, 100_000_000_000_000, 1, status)
            for name, status in status_by_name.items()}


# ---------------- what is an activation ----------------

def churn(added=(), removed=(), changed=(), **kwargs):
    return PoolChanges(list(added), list(removed), list(changed), **kwargs)


def test_activated_are_the_pools_that_are_open_now():
    opened = PoolChange('BTC.BTC', 'staged', 'available')
    new_open = PoolChange('ETH.ETH', 'available', 'available')  # appeared already open
    new_staged = PoolChange('DOGE.DOGE', 'staged', 'staged')
    suspended = PoolChange('LTC.LTC', 'available', 'suspended')
    removed = PoolChange('BCH.BCH', 'available', 'available')  # was open, is gone: not an activation
    pc = churn(added=[new_open, new_staged], removed=[removed], changed=[opened, suspended])

    assert pc.activated == [new_open, opened]
    rest = pc.without(pc.activated)
    assert rest.pools_added == [new_staged]
    assert rest.pools_removed == [removed]
    assert rest.pools_changed == [suspended]
    assert not churn(changed=[opened]).without([opened]).any_changed

    only = pc.only(opened)
    assert (only.pools_added, only.pools_removed, only.pools_changed) == ([], [], [opened])


def test_deprecated_enabled_status_counts_too():
    assert churn(changed=[PoolChange('BTC.BTC', 'bootstrap', 'Enabled')]).activated


@pytest.mark.asyncio
async def test_notifier_attaches_the_pools_and_the_price():
    class Logos:  # the check of the logos is in test_pool_logos.py; here it must not touch the disk or the network
        async def ensure_logo(self, logo):
            return ''

    notifier = PoolChurnNotifier(SimpleNamespace(cfg=RUNTIME_CFG, db=FakeDB(), flagship=None), logo_downloader=Logos())
    sent = []

    class Listener:
        async def on_data(self, sender, data):
            sent.append(data)

    notifier.add_subscriber(Listener())

    class Holder:
        usd_per_rune = 2.5

        def __init__(self, pools):
            self.pool_info_map = pools

    await notifier.on_data(None, Holder(make_pools(**{'BTC.BTC': 'staged'})))  # the first look only remembers
    after = make_pools(**{'BTC.BTC': 'available'})
    await notifier.on_data(None, Holder(after))

    assert len(sent) == 1
    assert sent[0].activated == [PoolChange('BTC.BTC', 'staged', 'available')]
    assert sent[0].pool_info_map is after
    assert sent[0].usd_per_rune == 2.5


# ---------------- the card parameters ----------------

def test_short_contract():
    assert short_contract('0X8AC76A51CC950D9822D68B83FE1AD97B32CD580D') == '0x8AC7…580D'
    assert short_contract('') == ''
    assert short_contract('TR7NH') == 'TR7NH'  # nothing to shorten


def test_card_of_a_token():
    pools = make_pools(**{BSC_USDC: 'available', 'BTC.BTC': 'available', 'DOGE.DOGE': 'staged'})
    card = build_pool_activated_card(BSC_USDC, pools, 2.0, EnglishLocalization(CFG), chain_logo='BSC.BNB')
    card = json.loads(json.dumps(card))  # the parameters travel to the renderer as JSON

    assert card['ticker'] == 'USDC'
    assert card['pool_label'] == 'BSC.USDC'
    assert card['contract'] == '0x8AC7…580D'
    assert card['asset_logo'] == BSC_USDC
    assert card['chain_logo'] == 'BSC.BNB'
    assert card['t']['title'] == 'NEW POOL'
    # the depth is both sides in dollars, the price is a RUNE over the asset, only the open pools are counted
    assert card['stats'] == [
        {'label': 'Pool depth', 'value': '$4.0M'},
        {'label': 'Price', 'value': '$2.0'},
        {'label': 'Active pools', 'value': '2'},
    ]


def test_card_leaves_out_what_is_not_known():
    loc = RussianLocalization(CFG)
    # no RUNE price: the pool numbers go, the count stays
    card = build_pool_activated_card('BTC.BTC', make_pools(**{'BTC.BTC': 'available'}), 0.0, loc)
    assert [s['label'] for s in card['stats']] == ['Активных пулов']
    assert card['contract'] == '' and card['chain_logo'] == ''
    assert card['t']['title'] == 'НОВЫЙ ПУЛ'

    # no pools at all: no numbers, the card is still there
    card = build_pool_activated_card('BTC.BTC', None, 2.0, loc)
    assert card['stats'] == []

    # the pool is not in the map
    card = build_pool_activated_card('BTC.BTC', make_pools(**{'ETH.ETH': 'available'}), 2.0, loc)
    assert [s['label'] for s in card['stats']] == ['Активных пулов']


def test_card_filename():
    assert pool_activated_card_filename(BSC_USDC).startswith('THORChain-pool-USDC-')
    assert pool_activated_card_filename(BSC_USDC).endswith('.png')


# ---------------- the template ----------------

@pytest.fixture(scope='module')
def renderer():
    pytest.importorskip('playwright')
    from renderer.engine import RendererEngine
    return RendererEngine(templates_dir=os.path.join(os.path.dirname(__file__), '..', 'renderer', 'templates'))


@pytest.mark.parametrize('pool, pools, usd_per_rune, loc', [
    (BSC_USDC, make_pools(**{BSC_USDC: 'available'}), 2.0, EnglishLocalization(CFG)),
    ('BTC.BTC', make_pools(**{'BTC.BTC': 'available'}), 0.0, RussianLocalization(CFG)),
    ('ETH.WSTETH-0X7F39C581F595B53C5CB19BD0B3F8DA6C935E2CA0', None, 0.0, EnglishLocalization(CFG)),
], ids=['token', 'ru-no-price', 'long-name-no-pools'])
def test_template_renders(renderer, pool, pools, usd_per_rune, loc):
    params = json.loads(json.dumps(build_pool_activated_card(pool, pools, usd_per_rune, loc)))
    result = renderer.render_template_to_html(POOL_ACTIVATED_TEMPLATE, params)
    assert (result.viewport_width, result.viewport_height) == (1200, 1200)
    html = result.html_content
    assert params['t']['activated'] in html and params['ticker'] in html
    for s in params['stats']:
        assert s['label'] in html and s['value'] in html
    assert ('class="stats"' in html) == bool(params['stats'])


def test_template_renders_the_demos(renderer):
    from renderer.demo import load_demo
    for name in ('pool_activated', 'pool_activated_ru'):
        demo = load_demo(name)
        assert demo['template_name'] == POOL_ACTIVATED_TEMPLATE
        html = renderer.render_template_to_html(demo['template_name'], demo['parameters']).html_content
        assert demo['parameters']['t']['activated'] in html


# ---------------- what is posted ----------------

class FakeBroadcaster:
    """Records what would be posted in English: (msg_type, the message)"""

    def __init__(self):
        self.posted = []
        self.loc = EnglishLocalization(CFG)

    async def broadcast_to_all(self, msg_type, f, *args):
        if f.__name__ == 'notification_text_pool_churn':  # a method of the localization
            message = f(self.loc, *args)
        else:
            message = await f(self.loc)
        self.posted.append((msg_type, message))


def make_presenter(use_renderer=True, fail=False):
    deps = SimpleNamespace(cfg=RUNTIME_CFG, broadcaster=FakeBroadcaster(), name_service=None)
    presenter = AlertPresenter(deps)
    presenter.use_renderer = use_renderer
    rendered = []

    async def render(loc, event, change):
        if fail:
            raise ValueError('renderer is down')
        rendered.append(change.pool_name)
        return b'png', f'{change.pool_name}.png'

    presenter.render_pool_activated = render
    return presenter, deps.broadcaster.posted, rendered


def mixed_event():
    return churn(
        added=[PoolChange('DOGE.DOGE', 'staged', 'staged'), PoolChange('ETH.ETH', 'available', 'available')],
        changed=[PoolChange('BTC.BTC', 'staged', 'available'), PoolChange('LTC.LTC', 'available', 'suspended')],
    )


@pytest.mark.asyncio
async def test_every_activated_pool_gets_its_own_card_then_the_rest_goes_as_text():
    presenter, posted, rendered = make_presenter()
    await presenter._handle_pool_churn(mixed_event())

    assert rendered == ['ETH.ETH', 'BTC.BTC']  # one after another
    assert [t for t, _ in posted] == ['public:pool_churn:activated'] * 2 + ['public:pool_churn']

    eth, btc, rest = [m for _, m in posted]
    assert all(isinstance(m, BoardMessage) and m.photo == b'png' for m in (eth, btc))
    assert eth.photo_file_name == 'ETH.ETH.png'
    assert 'ETH' in eth.text and 'Now Active' in eth.text and 'BTC' not in eth.text
    assert 'BTC' in btc.text and 'Now Active' in btc.text and 'ETH' not in btc.text
    # the pool that was not activated is told in text only
    assert isinstance(rest, str)
    assert 'DOGE' in rest and 'LTC' in rest and 'Now Active' not in rest and 'BTC' not in rest


@pytest.mark.asyncio
async def test_nothing_but_activations_leaves_no_text():
    presenter, posted, _ = make_presenter()
    await presenter._handle_pool_churn(churn(changed=[PoolChange('BTC.BTC', 'staged', 'available')]))
    assert [t for t, _ in posted] == ['public:pool_churn:activated']


@pytest.mark.asyncio
async def test_no_activation_is_one_text_as_before():
    presenter, posted, rendered = make_presenter()
    await presenter._handle_pool_churn(churn(changed=[PoolChange('LTC.LTC', 'available', 'suspended')]))
    assert not rendered
    assert [t for t, _ in posted] == ['public:pool_churn']
    assert 'LTC' in posted[0][1]


@pytest.mark.asyncio
async def test_without_the_renderer_everything_stays_in_one_text():
    presenter, posted, rendered = make_presenter(use_renderer=False)
    await presenter._handle_pool_churn(mixed_event())
    assert not rendered
    assert [t for t, _ in posted] == ['public:pool_churn']
    assert all(name in posted[0][1] for name in ('DOGE', 'ETH', 'BTC', 'LTC'))


@pytest.mark.asyncio
async def test_a_card_that_fails_is_still_announced_as_text():
    presenter, posted, _ = make_presenter(fail=True)
    await presenter._handle_pool_churn(churn(changed=[PoolChange('BTC.BTC', 'staged', 'available')]))
    assert len(posted) == 1
    assert isinstance(posted[0][1], str) and 'BTC' in posted[0][1] and 'Now Active' in posted[0][1]
