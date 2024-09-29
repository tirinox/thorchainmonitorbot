from lib.texts import shorten_text


def test_shorten_text_1():
    assert shorten_text('') == ''
    assert shorten_text(None) == 'None'

    assert shorten_text("foo bar", 3) == '...'
    assert shorten_text("foo bar", 6) == 'foo...'
    assert shorten_text("foo bar", 7) == 'foo bar'
    assert shorten_text("foo bar", 8) == 'foo bar'
    assert shorten_text("foo bar", 0) == 'foo bar'

    assert shorten_text("foo bar", 6, end='$$$') == 'foo$$$'
    assert shorten_text("foo bar", 5, end='$$$') == 'fo$$$'
