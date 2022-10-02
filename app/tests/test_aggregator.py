import pytest

from services.lib.aggregator import AggregatorResolver
from services.lib.constants import Chains
from services.lib.web3_helper import TokenList


@pytest.fixture(scope='module')
def aggr() -> AggregatorResolver:
    return AggregatorResolver('../data/token_list/aggregator_list.txt')


def test_loading(aggr):
    assert len(aggr) == 18
    assert len(aggr.by_chain) == 2
    assert set(aggr.by_chain.keys()) == {Chains.ETH, Chains.AVAX}


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
def test_aggregator_fuzzy_search(address, name, aggr):
    result = aggr.search_aggregator_address(address)
    if name is None:
        assert result is None
    else:
        assert result
        found_name, chain, found_address = result
        assert chain == Chains.ETH
        assert found_name == name


def test_token_list():
    t_avax = TokenList(TokenList.DEFAULT_TOKEN_LIST_AVAX_PATH[3:], Chains.AVAX)
    assert len(t_avax) > 0

    t1 = t_avax['0x152b9d0FdC40C096757F570A51E494bd4b943E50']
    assert t1.logoURI == 'https://raw.githubusercontent.com/traderjoe-xyz/joe-tokenlists/main/logos/0x152b9d0FdC40C096757F570A51E494bd4b943E50/logo.png'
    assert t1.decimals == 8
    assert t1.name == 'Bitcoin'
    assert all((t.chain_id == 43114 or t.chain_id == 4) for t in t_avax.tokens.values())

    t_eth = TokenList(TokenList.DEFAULT_TOKEN_LIST_ETH_PATH[3:], Chains.ETH)
    assert len(t_eth) > 0

    assert t_eth['0x5dbcF33D8c2E976c6b560249878e6F1491Bca25c'].name == 'yearnCurve.fiyDAIyUSDCyUSDTyTUSD'
    assert t_eth['0x5dbcF33D8c2E976c6b560249878e6F1491Bca25c'].symbol == 'yUSD'
