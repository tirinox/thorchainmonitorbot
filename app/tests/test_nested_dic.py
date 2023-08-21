import pytest
import ujson

from services.lib.utils import nested_set, nested_get, make_nested_default_dict


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


def unnest(d):
    return ujson.loads(ujson.dumps(d))


def test_make_nested_default_dict():
    assert make_nested_default_dict({}) == {}
    assert make_nested_default_dict({
        'foo': 'bar'
    }) == {'foo': 'bar'}
    assert make_nested_default_dict({
        'foo': {'bar': 'del'},
    }) == {'foo': {'bar': 'del'}}
    d = make_nested_default_dict({})
    d['x']['y']['z'] = 25
    assert d['x']['y']['z'] == 25
    assert d == {'x': {'y': {'z': 25}}}
    d['x']['gram'] = 200
    assert d == {'x': {'y': {'z': 25}, 'gram': 200}}
    assert unnest(d) == d


def test_make_nested_default_dict2():
    nd = make_nested_default_dict({
        'old': {
            '1': 10
        }
    })
    nd['1']['2']['3'] = 'hello'
    nd['1']['2']['4'] = 'bye'
    nd['2']['5'] = 'foo'
    assert nd == {
        'old': {'1': 10},
        '1': {
            '2': {
                '3': 'hello',
                '4': 'bye'
            },
        },
        '2': {'5': 'foo'}
    }
