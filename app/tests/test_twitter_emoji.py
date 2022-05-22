from services.dialog.twitter.text_length import twitter_text_length, twitter_cut_text
from services.lib.money import EMOJI_SCALE
from services.lib.texts import progressbar


def test_emoji_text_length():
    assert twitter_text_length('') == 0
    assert twitter_text_length('Hello') == 5
    assert twitter_text_length('💎') == 2
    assert twitter_text_length('-💎-123') == 7
    assert twitter_text_length('📈🛡👥') == 6

    for _, emo in EMOJI_SCALE:
        assert twitter_text_length(emo) == 2

    assert twitter_text_length(progressbar(20, 30, 15)) == 15


def test_twitter_cut_length():
    assert len(twitter_cut_text('12345678', 6)) == 6
    assert len(twitter_cut_text('12345678', 100)) == 8
    assert len(twitter_cut_text('', 100)) == 0

    assert twitter_cut_text('test🔀', 4) == 'test'
    assert twitter_cut_text('test🔀', 5) == 'test'
    assert twitter_cut_text('test🔀', 6) == 'test🔀'
    assert twitter_cut_text('test🔀Foo', 6) == 'test🔀'
    assert twitter_cut_text('test🔀Foo', 7) == 'test🔀F'

    assert twitter_cut_text('➕🌊', 1) == ''
    assert twitter_cut_text('➕🌊', 2) == '➕'
    assert twitter_cut_text('➕🌊', 3) == '➕'
    assert twitter_cut_text('➕🌊', 4) == '➕🌊'
