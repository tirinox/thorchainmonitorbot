import pytest

from services.lib.config import Config


def test_cfg1():
    c = Config(name='./tests/test_config.yaml')
    assert c.get_pure('thor') == c.thor.get()
    e = c.thor.bool_value
    assert isinstance(e, bool) and e

    assert c.get('thor.network_id') == "chaosnet-multi"
    assert c.get('unknown.path', 888) == 888
    assert c.get('unknown.path.deeper', 'str') == 'str'

    with pytest.raises(KeyError):
        c.get('unknown.path.deeper')

    assert c.foo[2].x == 12
    assert c.foo[0].y == 20

    with pytest.raises(IndexError):
        assert c.foo[3]