from services.lib.texts import split_by_camel_case


def test_cc():
    assert split_by_camel_case('TSNSomethingNewX') == 'TSN Something New X'
    assert split_by_camel_case('TABC') == 'TABC'
    assert split_by_camel_case('SexOnTheBeach') == 'Sex On The Beach'
