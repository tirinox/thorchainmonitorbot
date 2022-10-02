import pytest

from services.lib.aggregator import AggregatorResolver, AggregatorContract
from services.lib.config import Config
from services.lib.constants import Chains
from services.lib.web3_helper import TokenList, Web3Helper


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

    assert t_eth.fuzzy_search('a192D')[0].symbol == 'USDN'
    assert t_eth.fuzzy_search('A192d')[0].symbol == 'USDN'
    assert t_eth.fuzzy_search('A192d')[0].address == '0x674C6Ad92Fd080e4004b2312b45f796a192D27a0'
    assert not t_eth.fuzzy_search('abcdef')

    assert t_eth.fuzzy_search('0x45804880De22913dAFE09f4980848ECE6EcbAf78')[0].symbol == 'PAXG'
    assert t_eth.fuzzy_search('0x0000000000004946c0e9F43F4Dee607b0eF1fA1c')[0].symbol == 'CHI'


SWAP_IN_EXAMPLE_INPUT = '0xe4d0c7f0000000000000000000000000d37bbe5744d730a1d98d8dc97c42f0ca46ad7146000000000000000000000000bd0030184a4f177b0b0ad7da32fa1868bbf364d100000000000000000000000000000000000000000000000000000000000000e00000000000000000000000002260fac5e5542a773aa44fbcfedf7c193bc2c59900000000000000000000000000000000000000000000000000000000016142f400000000000000000000000000000000000000000000000000000000015914d70000000000000000000000000000000000000000000000000000000063213eb100000000000000000000000000000000000000000000000000000000000000413d3a4254432e4254433a62633171363966796e636639783873706371637376747135656b37346a7973796535646a347a67366c383a32323631353235363a743a3000000000000000000000000000000000000000000000000000000000000000'


@pytest.fixture(scope='module')
def w3_helper():
    return Web3Helper(Config(data={
        'infura': {
        }
    }))


@pytest.mark.asyncio
async def test_decode_input(w3_helper):
    AggregatorContract.DEFAULT_ABI_AGGREGATOR = AggregatorContract.DEFAULT_ABI_AGGREGATOR[3:]  # fix ../

    aggc = AggregatorContract(w3_helper)
    func, args = aggc.decode_input(SWAP_IN_EXAMPLE_INPUT)

    assert func == 'swapIn'

    assert args.tc_router == '0xD37BbE5744D730a1d98d8DC97c42F0Ca46aD7146'
    assert args.tc_vault == '0xBD0030184a4f177b0B0AD7da32Fa1868bbf364d1'
    assert args.tc_memo == '=:BTC.BTC:bc1q69fyncf9x8spcqcsvtq5ek74jysye5dj4zg6l8:22615256:t:0'
    assert args.target_token == '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599'
    assert args.amount == 23151348
