import asyncio
import logging

from services.dialog.twitter.text_length import twitter_text_length
from services.dialog.twitter.twitter_bot import TwitterBot
from services.lib.config import Config
from services.lib.utils import setup_logs


async def main():
    setup_logs(logging.INFO)
    cfg = Config()
    # twitter_bot = TwitterBotMock(cfg)
    twitter_bot = TwitterBot(cfg)
    await twitter_bot.post('Integrating the code...')


MSG = """📍 BNB.Rune:
Circulating: 11.2Mᚱ (2.24 %)
Locked: 25.9Mᚱ (5.19 %)
Total: 37.1Mᚱ (7.43 %)

📍 ETH.Rune:
Circulating: 4.6Mᚱ (0.914 %)
Locked: 62.0ᚱ (0.0000 %)
Total: 4.6Mᚱ (0.914 %)

📍 Native RUNE:
Circulating: 304.8Mᚱ (61.0 %)
Locked: 179.0Mᚱ (35.8 %)
Total: 483.8Mᚱ (96.8 %)"""

if __name__ == '__main__':
    print(twitter_text_length(MSG))
    asyncio.run(main())
