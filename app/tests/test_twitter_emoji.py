import json

import pytest

from comm.twitter.text_length import twitter_text_length, twitter_cut_text, \
    twitter_intelligent_text_splitter, abbreviate_some_long_words, TWITTER_T_CO_LENGTH, TWITTER_T_CO_EXAMPLE
from comm.twitter.twitter_bot import TwitterBot
from lib.config import Config
from lib.date_utils import HOUR, now_ts
from lib.money import EMOJI_SCALE
from lib.texts import progressbar, find_country_emoji


class _FakeRedis:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value):
        self.data[key] = value


class _FakeDB:
    def __init__(self):
        self.redis = _FakeRedis()

    async def get_redis(self):
        return self.redis


def _make_cfg():
    return Config(data={
        'twitter': {
            'max_length': 280,
            'full_symbol_cooldown': '12h',
            'bot': {
                'consumer_key': '1',
                'consumer_secret': '2',
                'access_token': '3',
                'access_token_secret': '4',
                'client_id': '5',
                'client_secret': '6',
                'bearer_token': '7',
            }
        }
    })


def _make_twitter_bot(db=None):
    return TwitterBot(_make_cfg(), db=db)


def test_emoji_text_length():
    assert twitter_text_length('') == 0
    assert twitter_text_length('Hello') == 5
    assert twitter_text_length('💎') == 2
    assert twitter_text_length('-💎-123') == 7
    assert twitter_text_length('📈🛡👥') == 6

    for _, emo in EMOJI_SCALE:
        assert twitter_text_length(emo) == 2

    assert twitter_text_length(progressbar(20, 30, 15)) == 15


def test_twitter_text_length_url():
    assert twitter_text_length(
        'https://stackoverflow.com/questions/11331982/how-to-remove-any-url-within-a-string-in-python') \
           == TWITTER_T_CO_LENGTH
    assert twitter_text_length(TWITTER_T_CO_EXAMPLE) == TWITTER_T_CO_LENGTH
    assert twitter_text_length(
        "Hello https://www.duolingo.com/learn and https://etherscan.io/gastracker\nhttps://etherscan.io/gastracker#gassender") \
           == len(f"Hello {TWITTER_T_CO_EXAMPLE} and {TWITTER_T_CO_EXAMPLE}\n"
                  f"{TWITTER_T_CO_EXAMPLE}")


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


def test_split_message():
    f = twitter_intelligent_text_splitter
    assert f(['AAA', '', 'CCC', ''], 10) == ['AAACCC']
    assert f(['AAA', 'BBB', 'CCC', 'DDD'], 10) == ['AAABBBCCC', 'DDD']
    assert f(['A' * 20, 'BBB', 'CCC', 'DDD'], 10) == ['A' * 10, 'BBBCCCDDD']
    assert f(['A' * 11, 'CCCC', 'B' * 20], 10) == ['A' * 10, 'CCCC', 'B' * 10]
    assert f(['AAA', 'BBB', 'CCC', 'DDD'], 3) == ['AAA', 'BBB', 'CCC', 'DDD']
    assert f(['AAA', 'BB', 'CC', 'DDD'], 3) == ['AAA', 'BB', 'CC', 'DDD']
    assert f(['AAA', 'B', 'C', 'D', 'E'], 3) == ['AAA', 'BCD', 'E']
    assert f(['AAA', 'B', 'C', 'D', 'E' * 20], 3) == ['AAA', 'BCD', 'E' * 3]


def test_country_codes():
    assert find_country_emoji('ag') == '🇦🇬'
    assert find_country_emoji('AG') == '🇦🇬'
    assert find_country_emoji('IE') == '🇮🇪'
    assert find_country_emoji('us') == '🇺🇸'
    assert find_country_emoji('') is None
    assert find_country_emoji('xxx') is None


def test_tw1():
    text = """🏛 Node-Mimir voting update

1. Next Chain ➔ "HAVEN": 32.6 % (31/95)
 ▰▰▰▰▰▰▱▱▱▱▱▱ 
2. Next Chain ➔ "BNB Chain (BSC)": 21.1 % (20/95)
 ▰▰▰▰▱▱▱▱▱▱▱▱ 
3. Next Chain ➔ "DASH": 10.5 % (10/95)👏"""
    assert twitter_text_length(text) == 189


def test_abbreviate():
    text = """💎 Total Rune switched to native: 484.3Mᚱ (97.0 %)
📈 Bonding APY is 8.62%(↑ +0.0184%) and Liquidity APY is 14.1%(↓ -0.0563%).
👥 Daily users: 405(↓ -2), monthly users: 3965(↑ +299) 🆕"""
    original_length = twitter_text_length(text)
    shortened_text = abbreviate_some_long_words(text)

    print(shortened_text)

    assert twitter_text_length(shortened_text) < original_length


def test_twitter_symbol_rewrite_preserves_rune_once():
    bot = _make_twitter_bot()

    text = 'Buy $RUNE, pair it with $BTC, and mention $RUNE again.'
    prepared, used = bot.rewrite_twitter_text(text, allow_full_rune=True)

    assert prepared == 'Buy $RUNE, pair it with BTC, and mention RUNE again.'
    assert used is True


@pytest.mark.asyncio
async def test_twitter_symbol_rewrite_respects_cooldown_with_db():
    db = _FakeDB()
    bot = _make_twitter_bot(db)

    assert await bot.prepare_twitter_text('First $RUNE post and $ETH') == 'First $RUNE post and ETH'
    assert await bot.prepare_twitter_text('Second $RUNE post and $BTC') == 'Second RUNE post and BTC'

    cooldown_key = bot.full_rune_symbol_cd.get_key(bot.FULL_RUNE_COOLDOWN_KEY)
    db.redis.data[cooldown_key] = json.dumps({'time': now_ts() - 13 * HOUR, 'count': 0})

    assert await bot.prepare_twitter_text('Third $RUNE post') == 'Third $RUNE post'


def test_twitter_symbol_rewrite_only_targets_valid_lengths():
    bot = _make_twitter_bot()

    text = 'Keep $A and $ABCDEFX untouched, but strip $BTC.'
    prepared, used = bot.rewrite_twitter_text(text, allow_full_rune=False)
    assert prepared == 'Keep $A and $ABCDEFX untouched, but strip BTC.'
    assert used is False


