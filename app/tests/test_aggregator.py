import pytest

from services.lib.constants import Chains
from services.lib.memo import AggregatorResolver


@pytest.mark.parametrize(('address', 'name'), [
    ('0x7C38b8B2efF28511ECc14a621e263857Fb5771d3', 'TSAggregatorUniswapV3-500'),
    ('7c3', 'TSAggregatorUniswapV3-500'),
    ('1D3', 'TSAggregatorUniswapV3-500'),
    ('983976529', 'TSAggregator SUSHIswap'),
    ('5dA', 'TSAggregator SUSHIswap'),
    ('6cFD3', 'TSAggregator SUSHIswap'),
    ('6Cfd3', 'TSAggregator SUSHIswap'),
    ('0x2a781', 'RangoThorchainOutputAggUniV3'),
    ('xyz', None),
    ('0x35919b3929De1319', None),
])
def test_aggregator_fuzzy_search(address, name):
    result = AggregatorResolver.search_aggregator_address(address)
    if name is None:
        assert result is None
    else:
        found_name, chain, found_address = result
        assert chain == Chains.ETH
        assert found_name == name
