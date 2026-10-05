import json
import os
from types import SimpleNamespace

import pytest

from comm.localization.eng_base import EnglishLocalization
from comm.localization.rus import RussianLocalization
from comm.picture.lp_card import build_lp_add_card, LP_ADD_TEMPLATE, MEGA_SHARE
from lib.config import Config
from models.memo import ActionType
from notify.alert_presenter import AlertPresenter
from notify.channel import BoardMessage
from tests.test_pool_card import FakeBroadcaster, RUNTIME_CFG
from tools.debug.dbg_lp_card import make_lp_add_event, DEMOS

CFG = Config(name='./tests/test_config.yaml')
USDC = 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48'


def sym():
    return make_lp_add_event('BTC.BTC', 38_000, 0.41, 73_400, 45_000_000)


def asym():
    return make_lp_add_event(USDC, 0, 120_000, 1.0, 8_100_000)


def mega():  # the example of the chat: about $1.1K of pool, then $51K added
    return make_lp_add_event('ZEC.ZEC', 32_000, 18.0, 1_411, 52_100)


# ---------------- the parameters ----------------

def test_symmetric_add_into_a_deep_pool():
    card = build_lp_add_card(sym(), EnglishLocalization(CFG), 'thor1q...x9f2', '')
    assert card['ticker'] == 'BTC' and card['asset_logo'] == 'BTC.BTC'
    assert card['rune_amount'] == 38_000 and card['asset_amount'] == pytest.approx(0.41)
    assert card['total_usd'] == pytest.approx(card['rune_usd'] + card['asset_usd'])
    assert card['rune_usd'] == pytest.approx(38_000 * 0.8)
    assert card['depth_usd'] == pytest.approx(45_000_000)
    assert card['before_usd'] == pytest.approx(45_000_000 - card['total_usd'])
    assert card['share'] == pytest.approx(card['total_usd'] / 45_000_000 * 100)
    assert not card['mega'] and card['multiplier'] == 0
    assert card['t']['badge'] == 'Symmetric' and card['t']['title'] == 'LIQUIDITY ADDED'
    assert card['user_name'] == 'thor1q...x9f2'


def test_single_sided_add():
    card = build_lp_add_card(asym(), RussianLocalization(CFG), chain_logo='ETH.ETH')
    assert card['rune_amount'] == 0 and card['rune_usd'] == 0
    assert card['asset_usd'] == pytest.approx(120_000)
    assert card['t']['badge'] == 'Односторонне'
    assert card['t']['no_rune'] == 'без RUNE' and card['t']['pool'] == 'пул USDC'
    assert card['chain_logo'] == 'ETH.ETH'


def test_an_add_bigger_than_the_pool_celebrates():
    card = build_lp_add_card(mega(), EnglishLocalization(CFG))
    assert card['mega']
    assert card['share'] > MEGA_SHARE
    assert card['before_usd'] == pytest.approx(52_100 - card['total_usd'])
    assert card['multiplier'] == round(52_100 / card['before_usd']) == 47
    assert card['t']['badge'] == 'POOL ×47'
    assert build_lp_add_card(mega(), RussianLocalization(CFG))['t']['badge'] == 'ПУЛ ×47'


@pytest.mark.parametrize('added_of_depth, is_mega', [(0.49, False), (0.5, False), (0.51, True), (1.0, True)])
def test_mega_is_more_than_half_of_the_pool(added_of_depth, is_mega):
    # single-sided USDC at $1: the add is exactly that share of the depth after it
    event = make_lp_add_event(USDC, 0, 100_000 * added_of_depth, 1.0, 100_000)
    card = build_lp_add_card(event, EnglishLocalization(CFG))
    assert card['mega'] is is_mega


def test_the_first_liquidity_of_an_empty_pool_has_no_multiplier():
    card = build_lp_add_card(make_lp_add_event(USDC, 0, 100_000, 1.0, 100_000), EnglishLocalization(CFG))
    assert card['mega'] and card['before_usd'] == 0 and card['multiplier'] == 0
    assert card['t']['badge'] == 'Single-sided'  # no "POOL ×∞"


def test_without_the_pool_there_are_no_pool_numbers():
    event = sym()
    event.pool_info = None
    card = build_lp_add_card(event, EnglishLocalization(CFG))
    assert card['depth_usd'] == 0 and card['share'] == 0 and not card['mega']


# ---------------- the template ----------------

@pytest.fixture(scope='module')
def renderer():
    pytest.importorskip('playwright')
    from renderer.engine import RendererEngine
    return RendererEngine(templates_dir=os.path.join(os.path.dirname(__file__), '..', 'renderer', 'templates'))


@pytest.mark.parametrize('make_event', [sym, asym, mega])
def test_template_renders(renderer, make_event):
    params = json.loads(json.dumps(build_lp_add_card(make_event(), EnglishLocalization(CFG), 'thor1q...x9f2')))
    result = renderer.render_template_to_html(LP_ADD_TEMPLATE, params)
    assert (result.viewport_width, result.viewport_height) == (1280, 720)
    html = result.html_content
    assert params['t']['badge'] in html and 'thor1q...x9f2' in html
    # an arrow per side that was added; confetti only for a record
    assert html.count('marker-end=') == (params['rune_amount'] > 0) + (params['asset_amount'] > 0)
    assert ('id="party"' in html) == params['mega']
    if params['mega']:
        assert f'×{params["multiplier"]}' in html


def test_template_renders_the_demos(renderer):
    from renderer.demo import load_demo
    for name, *_ in DEMOS:
        demo = load_demo(name)
        assert demo['template_name'] == LP_ADD_TEMPLATE
        assert demo['parameters']['t']['title'] in renderer.render_template_to_html(LP_ADD_TEMPLATE, demo['parameters']).html_content


# ---------------- what is posted ----------------

def make_presenter(use_renderer=True, fail=False):
    deps = SimpleNamespace(cfg=RUNTIME_CFG, broadcaster=FakeBroadcaster(), name_service=None)
    presenter = AlertPresenter(deps)
    presenter.use_renderer = use_renderer

    async def load_names(addresses):
        return None

    async def render(loc, event, name_map):
        if fail:
            raise ValueError('renderer is down')
        return b'png', 'lp.png'

    presenter.load_names = load_names
    presenter.render_lp_add = render
    return presenter, deps.broadcaster


class TextBroadcaster(FakeBroadcaster):
    async def broadcast_to_all(self, msg_type, f, *args):
        if f.__name__ == 'notification_text_large_single_tx':
            self.posted.append((msg_type, f(self.loc, *args)))
        else:
            self.posted.append((msg_type, await f(self.loc)))


@pytest.mark.asyncio
@pytest.mark.parametrize('use_renderer, fail, photo', [(True, False, True), (True, True, False), (False, False, False)])
async def test_an_add_goes_with_its_card_or_as_the_old_text(use_renderer, fail, photo):
    presenter, _ = make_presenter(use_renderer, fail)
    presenter.broadcaster = TextBroadcaster()
    await presenter._handle_large_tx(mega())

    [(msg_type, message)] = presenter.broadcaster.posted
    assert msg_type == 'public:large_tx'  # the same type as before: its flags and stats stay
    assert isinstance(message, BoardMessage) == photo
    text = message.text if photo else message
    assert 'Liquidity added' in text or 'liquidity' in text.lower()


@pytest.mark.asyncio
async def test_a_withdraw_stays_a_text():
    presenter, _ = make_presenter()
    presenter.broadcaster = TextBroadcaster()
    event = mega()
    event.transaction.type = ActionType.WITHDRAW.value
    await presenter._handle_large_tx(event)
    assert isinstance(presenter.broadcaster.posted[0][1], str)


@pytest.mark.asyncio
async def test_render_gives_the_card_its_parameters():
    deps = SimpleNamespace(cfg=RUNTIME_CFG, broadcaster=FakeBroadcaster(), name_service=None)
    presenter = AlertPresenter(deps)
    sent = {}

    async def render(template, parameters):
        sent.update(template=template, **parameters)
        return b'png'

    presenter.renderer = SimpleNamespace(render=render)
    photo, name = await presenter.render_lp_add(EnglishLocalization(CFG), mega(), None)
    assert photo == b'png' and name.startswith('THORChain-liquidity-ZEC-')
    assert sent['template'] == LP_ADD_TEMPLATE and sent['mega'] and sent['multiplier'] == 47
    assert sent['user_name'] == 'thor1q ... x9f2'
