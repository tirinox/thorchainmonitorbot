import asyncio
import logging

from services.dialog.twitter.twitter_bot import TwitterBotMock
from services.lib.config import Config
from services.lib.utils import setup_logs


async def main():
    setup_logs(logging.INFO)
    cfg = Config()
    twitter_bot = TwitterBotMock(cfg)
    # twitter_bot = TwitterBot(cfg)
    await twitter_bot.post('Integrating the code...')


if __name__ == '__main__':
    asyncio.run(main())
