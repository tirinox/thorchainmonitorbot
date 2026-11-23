import json
import os

import pytest

from api.aionode.types import ThorPool
from models.pool_info import parse_thor_pools
from models.price import PriceHolder


@pytest.fixture(scope='module')
def sample_price_holder() -> PriceHolder:
    this_path = os.path.dirname(os.path.abspath(__file__))
    with open(f'{this_path}/sample_data/pools.json', 'r') as f:
        data = f.read()
        ph = PriceHolder()
        pool_map = parse_thor_pools([ThorPool.from_json(p) for p in json.loads(data)])
        ph.update_pools(pool_map)

        return ph


def test_fuzzy_pool_search(sample_price_holder: PriceHolder):
    assert len(sample_price_holder.pool_info_map) == 45

    assert sample_price_holder.pool_fuzzy_first('g') == 'GAIA.ATOM'


def test_short_codes_of_new_chains(sample_price_holder: PriceHolder):
    # thornode's short codes win over a fuzzy match: "z" once found TRON.USDT-...Z... instead of ZEC
    for code, asset in [('z', 'ZEC.ZEC'), ('m', 'XMR.XMR'), ('o', 'SOL.SOL'), ('ta', 'TAO.TAO'),
                        ('p', 'POL.POL'), ('u', 'SUI.SUI'), ('do', 'DOT.DOT'), ('ad', 'ADA.ADA')]:
        assert sample_price_holder.pool_fuzzy_first(code) == asset
