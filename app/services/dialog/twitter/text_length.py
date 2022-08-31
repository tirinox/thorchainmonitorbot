import re

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


def twitter_intelligent_text_splitter(parts, max_len=TWITTER_LIMIT_CHARACTERS):
    parts = filter(bool, parts)

    messages = []
    this_message_len = 0
    this_message_text = ''
    for part in parts:
        part_len = twitter_text_length(part)
        if part_len > max_len:
            part_len = max_len
            part = twitter_cut_text(part, max_len)

        this_message_len += part_len
        if this_message_len > max_len:
            messages.append(this_message_text)
            this_message_len = part_len
            this_message_text = part
        else:
            this_message_text += part
    if this_message_text:
        messages.append(this_message_text)

    return messages


re_english_words = re.compile(r"[a-zA-Z]{5,10}")


def abbreviate_some_long_words(text: str, regular_expression=re_english_words):
    def replacer(match: re.Match):
        b, e = match.regs[0]
        return match.string[b:e][:4] + '.'

    return regular_expression.sub(replacer, text)
