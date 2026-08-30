import pytest

from lib.constants import Chains, MINUTE


@pytest.mark.parametrize('address, expected_chain', [
    ('4' + '1' * 94, Chains.XMR),
    ('8' + '1' * 94, Chains.XMR),
    ('9' + '1' * 105, Chains.XMR),
    ('T' + '1' * 33, Chains.TRON),
    ('t1' + '1' * 33, Chains.ZEC),
])
def test_detect_chain(address, expected_chain):
    assert Chains.detect_chain(address) == expected_chain


def test_detect_chain_rejects_short_privacy_addresses():
    assert Chains.detect_chain('4' + '1' * 20) == ''
    assert Chains.detect_chain('t1' + '1' * 10) == ''


def test_privacy_chain_block_times():
    assert Chains.block_time_default(Chains.XMR) == 2 * MINUTE
    assert Chains.block_time_default(Chains.ZEC) == 75.0

