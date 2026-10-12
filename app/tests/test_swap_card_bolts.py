import os
import re

import pytest

from renderer.demo import available_demo_templates, load_demo

SWAP_DEMOS = sorted(n for n in available_demo_templates() if n.startswith('swap_'))


@pytest.fixture(scope='module')
def renderer():
    pytest.importorskip('playwright')
    from renderer.engine import RendererEngine
    return RendererEngine(templates_dir=os.path.join(os.path.dirname(__file__), '..', 'renderer', 'templates'))


@pytest.mark.parametrize('name', SWAP_DEMOS)
def test_swap_cards_draw_bolts_in_place_of_arrows(renderer, name):
    demo = load_demo(name)
    p = demo['parameters']
    html = renderer.render_template_to_html(demo['template_name'], p).html_content
    kinds = re.findall(r'<svg class="bolt".*?data-kind="(\w+)"', html, re.S)

    if demo['template_name'] == 'swap_start.jinja2':
        # nothing has reached the affiliates and the destination yet
        assert kinds == ['main', 'pending', 'pending']
    else:
        to_affiliates = 'main' if p['affiliate_names'] else 'pending'
        source = ['refund', 'main'] if p.get('refund') else ['main']
        # a DEX aggregator before or after THORChain is a small bolt on the outer side of its logo
        dex_in, dex_out = (['main'] if p.get(leg) else [] for leg in ('dex_in', 'dex_out'))
        assert kinds == dex_in + source + [to_affiliates, 'main'] + dex_out
    assert 'static/js/bolts.js' in html
