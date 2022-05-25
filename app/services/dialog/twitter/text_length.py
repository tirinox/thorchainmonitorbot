from emoji import is_emoji

TWITTER_LIMIT_CHARACTERS = 280


def twitter_glyph_length(g):
    return 2 if is_emoji(g) else 1


def twitter_text_length(text):
    return sum(twitter_glyph_length(c) for c in text)


def twitter_cut_text(text, max_length):
    result, count = '', 0
    for c in text:
        delta = twitter_glyph_length(c)
        if count + delta > max_length:
            break
        count += delta
        result += c
    return result
