import pytest

from services.lib.utils import nested_set, nested_get


def test_get():
    assert nested_get({}, ()) is None
    assert nested_get({}, ('lol', 'foo')) is None
    assert nested_get({}, ('lol', 'foo'), 33) == 33

    dic = {
        "path": {
            "to": {
                "freedom": 'is here'
            }
        },
        'key': 'value'
    }

    assert nested_get(dic, ('path', 'to', 'freedom')) == 'is here'
    assert nested_get(dic, ('path', 'to', 'the moon'), 'rune') == 'rune'
    assert nested_get(dic, ('key',)) == 'value'
    assert nested_get(dic, (1, 2, 3, 4)) is None


def test_set():
    with pytest.raises(KeyError):
        assert nested_set({}, (), 1) == {}

    assert nested_set({}, ('path', 'to', 'freedom'), 1) == {'path': {'to': {'freedom': 1}}}
    assert nested_set({}, ('foo',), {'some': 'data'}) == {'foo': {'some': 'data'}}

    dic = {
        'your': {
            'dic': 10
        },
        'my': {
            'dic': 49
        }
    }
    nested_set(dic, ('my', 'dic'), {'foo': 100})
    assert dic['your']['dic'] == 10

    nested_set(dic, ('your', 'dic'), {'bar': 200})

    assert dic['my']['dic'] == {'foo': 100}
    assert dic['your']['dic'] == {'bar': 200}
