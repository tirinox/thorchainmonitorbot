import pytest

from api.midgard.name_service import AffiliateManager


@pytest.fixture(scope='module')
def aff_man():
    return AffiliateManager()


def test_known_code_resolves_to_name(aff_man):
    assert aff_man.get_affiliate_name('t1') == 'TrustWallet'
    assert aff_man.get_affiliate_name('w1') == 'THORWallet'


def test_unknown_thorname_is_capitalized(aff_man):
    assert aff_man.get_affiliate_name('foobar') == 'Foobar'


@pytest.mark.parametrize('address', [
    'thor18dvgrgpvxlh7rhhld4qjyrxs9c7tvwdakrkjm4',
    'THOR18DVGRGPVXLH7RHHLD4QJYRXS9C7TVWDAKRKJM4',
    'sthor1dheycdevq39qlkxs2a6wuuzyn4aqxhvepe6as4',
])
def test_unknown_thor_address_stays_lower_case(aff_man, address):
    name = aff_man.get_affiliate_name(address)
    assert name == name.lower()
    assert name.startswith(address.lower()[:5])


def test_thorname_starting_with_thor_is_still_capitalized(aff_man):
    assert aff_man.get_affiliate_name('thor1abc') == 'Thor1abc'
