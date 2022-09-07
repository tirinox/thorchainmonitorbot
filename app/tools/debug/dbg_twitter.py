import asyncio
import logging
import os

from localization.languages import Language
from services.dialog.twitter.twitter_bot import TwitterBot, TwitterBotMock
from services.lib.config import Config
from services.lib.utils import setup_logs
from services.notify.channel import BoardMessage, ChannelDescriptor
from tools.debug.dbg_supply_graph import get_supply_pic, save_and_show_supply_pic
from tools.lib.lp_common import LpAppFramework

MOCK = True


async def twitter_post_supply(bot: TwitterBot):
    app = LpAppFramework()
    async with app(brief=True):
        # configure
        app.deps.twitter_bot = bot
        app.deps.broadcaster.channels = [
            ChannelDescriptor('twitter', '', Language.ENGLISH_TWITTER)
        ]

        pic, pic_name = await get_supply_pic(app)
        save_and_show_supply_pic(pic)

        loc = app.deps.loc_man[Language.ENGLISH_TWITTER]
        b_message = BoardMessage.make_photo(pic, loc.SUPPLY_PIC_CAPTION)

        await app.deps.broadcaster.notify_preconfigured_channels(b_message)


async def main():
    setup_logs(logging.INFO)
    print(os.getcwd())
    cfg = Config('../../../temp/twitter.yaml')
    twitter_bot = TwitterBotMock(cfg) if MOCK else TwitterBot(cfg)

    await twitter_post_supply(twitter_bot)

    # await twitter_bot.post('Integrating the code...')


if __name__ == '__main__':
    asyncio.run(main())
