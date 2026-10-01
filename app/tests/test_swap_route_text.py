import os

from api.midgard.parser import MidgardParserV2
from comm.localization.eng_base import BaseLocalization
from lib.config import Config
from lib.constants import NetworkIdents
from lib.utils import load_json

# 26D5E260...: 150.1 ETH -> TRON.USDT in two legs, the affiliate fee paid out in RUNE to SwapKit and Bitget
PATH = os.path.join(os.path.dirname(__file__), 'sample_data', 'swap_two_legs_with_aff.json')


class Loc(BaseLocalization):
    pass


def load_swap():
    parser = MidgardParserV2(network_id=NetworkIdents.MAINNET)
    return parser.parse_tx_response(load_json(PATH)).txs[0]


def test_asset_summary_can_skip_affiliates():
    tx = load_swap()

    all_out = tx.get_asset_summary(out_only=True)
    assert set(all_out) == {'TRON.USDT-TR7NHQJEKQXGTCI8Q8ZY4PL8OTSZGJLJ6T', 'THOR.RUNE'}

    user_out = tx.get_asset_summary(out_only=True, skip_affiliates=True)
    assert list(user_out) == ['TRON.USDT-TR7NHQJEKQXGTCI8Q8ZY4PL8OTSZGJLJ6T']
    assert round(user_out['TRON.USDT-TR7NHQJEKQXGTCI8Q8ZY4PL8OTSZGJLJ6T'], 2) == 265587.74


def test_swap_route_output_has_no_affiliate_payout():
    route = Loc(Config(data={})).format_swap_route(load_swap(), usd_per_rune=0.79)
    _, output = route.split('⚡')
    assert '<b>265.6K</b> TRON.USDT' in output
    assert 'RUNE' not in output
