import json
import os

import pytest

from services.lib.midgard.parser import MidgardParserV1, MidgardParserV2
from services.lib.constants import NetworkIdents, THOR_DIVIDER
from services.models.tx import SUCCESS

PATH = './app/tests/tx_examples'
DIV = THOR_DIVIDER


def inner_example_tx_gen(name):
    with open(os.path.join(PATH, name), 'r') as f:
        return json.load(f)


@pytest.fixture
def example_tx_gen():
    return inner_example_tx_gen


def test_parser_v1_swap(example_tx_gen):
    txs = example_tx_gen(name='v1_swap.json')
    p = MidgardParserV1(network_id=NetworkIdents.CHAOSNET_BEP2CHAIN)
    res = p.parse_tx_response(txs)
    assert res
    assert res.tx_count == 50
    assert res.total_count == 211078
    t0 = res.txs[0]

    assert t0.status == SUCCESS
    assert t0.height == "2648585"
    assert t0.height_int == 2648585
    assert t0.date == "1613413527000000000"
    assert t0.pools == ['BNB.BNB']


def test_parser_v1_double_swap(example_tx_gen):
    txs = example_tx_gen(name='v1_dbl_swap.json')
    p = MidgardParserV1(network_id=NetworkIdents.CHAOSNET_BEP2CHAIN)
    res = p.parse_tx_response(txs)

    t0 = res.txs[0]
    assert t0.pools == ['BNB.BNB', 'BNB.FTM-A64']

    t1 = res.txs[1]
    assert t1.pools == ['BNB.BTCB-1DE', 'BNB.ETH-1C9']


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
