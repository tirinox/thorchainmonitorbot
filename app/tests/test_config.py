import sys

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


def _write_config(path, network_id):
    path.write_text(f'thor:\n  network_id: "{network_id}"\n')


@pytest.fixture
def default_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Config, 'DEFAULT_CONFIG_FILES', ['config.yaml'])
    _write_config(tmp_path / 'config.yaml', 'default')
    return tmp_path


def test_config_path_as_the_first_argument(default_config, monkeypatch):
    # the way the containers start: python main.py /config/config.yaml
    _write_config(default_config / 'custom.yml', 'from-argv')
    monkeypatch.setattr(sys, 'argv', ['main.py', str(default_config / 'custom.yml'), '--reload'])
    assert Config().network_id == 'from-argv'


@pytest.mark.parametrize('argv', [
    ['dbg_tool.py', 'thor1edd07q7q00hcjm5jg404g5jf84fuexqe93txsj', 'ETH.ETH'],
    ['dbg_tool.py', '28039404'],
    ['dashboard_api.py', '--reload'],
    ['main.py'],
])
def test_other_arguments_are_left_to_the_script(default_config, monkeypatch, argv):
    monkeypatch.setattr(sys, 'argv', argv)
    assert Config().network_id == 'default'


def test_no_config_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Config, 'DEFAULT_CONFIG_FILES', ['config.yaml'])
    monkeypatch.setattr(sys, 'argv', ['dbg_tool.py', 'thor1address'])
    with pytest.raises(FileNotFoundError, match='No config file'):
        Config()
