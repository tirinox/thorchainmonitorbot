from services.lib.utils import turn_dic_inside_out


def test1():
    assert turn_dic_inside_out({}) == {}
    assert turn_dic_inside_out({5: {6}}) == {6: {5}}
    assert turn_dic_inside_out({1: {10}, 2: {20}}) == {10: {1}, 20: {2}}
    assert turn_dic_inside_out({
        'A': {'1'},
        'B': set(),
        'C': {'1'},
        'D': {'1', '2'},
        'E': {'1', '2'},
        'F': {'1'},
    }) == {'1': {'A', 'C', 'D', 'E', 'F'}, '2': {'D', 'E'}}
