EMOJI_SCALE = [
    # negative
    (-50, '💥'), (-35, '👺'), (-25, '😱'), (-20, '😨'), (-15, '🥵'), (-10, '😰'), (-5, '😢'), (-3, '😥'), (-2, '😔'),
    (-1, '😑'), (0, '😕'),
    # positive
    (1, '😏'), (2, '😄'), (3, '😀'), (5, '🤗'), (10, '🍻'), (15, '🎉'), (20, '💸'), (25, '🔥'), (35, '🌙'), (50, '🌗'),
    (65, '🌕'), (80, '⭐'), (100, '✨'), (10000000, '⚡')
]

REAL_REGISTERED_ATH = 1.62  # BUSD / Rune

def emoji_for_percent_change(pc):
    for threshold, emoji in EMOJI_SCALE:
        if pc <= threshold:
            return emoji
    return EMOJI_SCALE[-1]  # last one
