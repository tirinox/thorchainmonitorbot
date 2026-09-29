import ujson

from lib.utils import make_nested_default_dict


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
