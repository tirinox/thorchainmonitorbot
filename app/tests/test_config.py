import pytest

from lib.config import Config
from lib.constants import THOR_ADDRESS_DICT, TREASURY_LP_ADDRESS


def test_cfg1():
    c = Config(name='./tests/test_config.yaml')
    assert c.get_pure('thor') == c.thor.get()
    e = c.thor.bool_value
    assert isinstance(e, bool) and e

    assert c.get('thor.network_id') == "chaosnet-multi"
    assert c.get('unknown.path', 888) == 888
    assert c.get('unknown.path.deeper', 'str') == 'str'

    with pytest.raises(LookupError):
        c.get('unknown.path.deeper')

    assert c.foo[2].x == 12
    assert c.foo[0].y == 20

    with pytest.raises(LookupError):
        assert c.foo[3]


def test_supply_tracked_addresses_fallback_to_defaults():
    c = Config(data={})

    assert c.thor_address_dict == THOR_ADDRESS_DICT


def test_supply_tracked_addresses_loaded_from_config():
    c = Config(data={
        'supply': {
            'tracked_addresses': {
                'thor1customreserve': {
                    'name': 'Custom Reserve',
                    'realm': 'Reserve',
                },
                'thor1customcex': {
                    'name': 'Custom CEX',
                    'realm': 'CEX',
                },
            },
        },
    })

    assert c.thor_address_dict == {
        'thor1customreserve': ('Custom Reserve', 'Reserve'),
        'thor1customcex': ('Custom CEX', 'CEX'),
    }


def test_treasury_lp_address_fallback_to_default():
    c = Config(data={})

    assert c.treasury_lp_address == TREASURY_LP_ADDRESS


def test_treasury_lp_address_loaded_from_config_and_updates_default_supply_map():
    custom_address = 'thor1customtreasurylp'
    c = Config(data={
        'supply': {
            'treasury_lp_address': custom_address,
        },
    })

    assert c.treasury_lp_address == custom_address
    assert TREASURY_LP_ADDRESS not in c.thor_address_dict
    assert c.thor_address_dict[custom_address] == ('Treasury LP', 'Treasury')
    assert len(c.thor_address_dict) == len(THOR_ADDRESS_DICT)

