import json
import os

import pytest

from services.lib.constants import NetworkIdents, THOR_DIVIDER
from services.lib.midgard.parser import MidgardParserV2

PATH = './app/tests/tx_examples'
DIV = THOR_DIVIDER


def inner_example_tx_gen(name):
    with open(os.path.join(PATH, name), 'r') as f:
        return json.load(f)


@pytest.fixture
def example_tx_gen():
    return inner_example_tx_gen


@pytest.mark.parametrize('fn', [
    'v2_add.json',
    'v2_swap.json',
    'v2_refund.json',
    'v2_withdraw.json',
])
def test_parser_v2_smoke(fn, example_tx_gen):
    txs = example_tx_gen(name=fn)
    p = MidgardParserV2(network_id=NetworkIdents.TESTNET_MULTICHAIN)
    res = p.parse_tx_response(txs)
    assert res.tx_count > 0
    assert res.total_count > 0
