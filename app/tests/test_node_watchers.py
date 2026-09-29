from lib.utils import parse_list_from_string


def test_multi_split():
    assert parse_list_from_string("") == []
    assert parse_list_from_string("\n") == []
    assert parse_list_from_string("\t") == []
    assert parse_list_from_string(",") == []
    assert parse_list_from_string("    ") == []
    assert parse_list_from_string(", , ; ; \n \t \n ; ,") == []
    assert parse_list_from_string("    ; ;    \n") == []
    assert parse_list_from_string("test") == ['test']
    assert parse_list_from_string("TeSt", lower=True) == ['test']
    assert parse_list_from_string(";TeSt,", upper=True) == ['TEST']
    assert parse_list_from_string("TeSt;fOo", upper=True) == ['TEST', 'FOO']

    assert parse_list_from_string("xqmm") == ["xqmm"]

    assert parse_list_from_string("thorA, THORB, tHorC", upper=True) == ['THORA', 'THORB', 'THORC']
    assert parse_list_from_string("thorA  , THORB    ; tHorC", upper=True) == ['THORA', 'THORB', 'THORC']
    assert parse_list_from_string("thorA  , THORB    ; tHorC", upper=True) == ['THORA', 'THORB', 'THORC']
    assert parse_list_from_string("   thorA  \n\n THORB\ttHorC", upper=True) == ['THORA', 'THORB', 'THORC']

    assert parse_list_from_string("   thorA  \n\n THORB\ttHorC") == ['thorA', 'THORB', 'tHorC']

    assert parse_list_from_string("   thorA  \n\n THORB\ttHorC") == ['thorA', 'THORB', 'tHorC']
    assert parse_list_from_string("   thorA  \n\n THORB\ttHorC") == ['thorA', 'THORB', 'tHorC']

    assert parse_list_from_string("""
      thora,
      ThorB
      thorc;foo
    """, upper=True) == ['THORA', 'THORB', 'THORC', 'FOO']
