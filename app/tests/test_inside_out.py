from services.lib.utils import invert_dict_of_iterables


def test1():
    assert invert_dict_of_iterables({}) == {}
    assert invert_dict_of_iterables({5: {6}}) == {6: {5}}
    assert invert_dict_of_iterables({1: {10}, 2: {20}}) == {10: {1}, 20: {2}}
    assert invert_dict_of_iterables({
        'A': {'1'},
        'B': set(),
        'C': {'1'},
        'D': {'1', '2'},
        'E': {'1', '2'},
        'F': {'1'},
    }) == {'1': {'A', 'C', 'D', 'E', 'F'}, '2': {'D', 'E'}}
