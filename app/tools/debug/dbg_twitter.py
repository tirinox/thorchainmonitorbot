import asyncio
import logging
import os

from comm.picture.price_picture import price_graph_from_db
from comm.twitter.twitter_bot import TwitterBot, TwitterBotMock
from comm.localization.languages import Language
from lib.config import Config
from lib.date_utils import DAY
from lib.utils import setup_logs
from notify.channel import BoardMessage, ChannelDescriptor
from notify.public.burn_notify import BurnNotifier
from tools.debug.dbg_supply_graph import get_supply_pic
from tools.lib.lp_common import LpAppFramework, save_and_show_pic

MOCK = True


async def twitter_post_supply(app: LpAppFramework):
    pic, pic_name = await get_supply_pic(app)
    save_and_show_pic(pic, name='supply')

    loc = app.deps.loc_man[Language.ENGLISH_TWITTER]
    b_message = BoardMessage.make_photo(pic, loc.SUPPLY_PIC_CAPTION)

    await app.deps.broadcaster.broadcast_to_all(b_message)


async def twitter_post_price(app: LpAppFramework):
    loc = app.deps.loc_man.default
    graph, graph_name = await price_graph_from_db(app.deps, loc, period=14 * DAY)

    await app.deps.broadcaster.broadcast_to_all(
        BoardMessage.make_photo(graph, caption='Rune price', photo_file_name=graph_name)
    )

    # await app.deps.broadcaster.notify_preconfigured_channels(
    #     BoardMessage('Test Twitter API v2')
    # )


async def twitter_post_burned_rune(app: LpAppFramework):
    await app.deps.last_block_fetcher.run_once()
    await app.deps.mimir_const_fetcher.run_once()
    await app.deps.pool_fetcher.run_once()
    notifier = BurnNotifier(app.deps)
    event = await notifier.get_event()
    photo, name = app.deps.alert_presenter.render_rune_burn_graph(event)
    loc = app.deps.loc_man.default
    text = loc.notification_rune_burn(event)
    await app.deps.broadcaster.broadcast_to_all(
        BoardMessage.make_photo(photo, caption=text, photo_file_name=name)
    )


async def main():
    app = LpAppFramework()

    async with app(brief=True):
        print(os.getcwd())
        cfg = Config('../../../temp/twitter.yaml')
        twitter_bot = TwitterBotMock(cfg) if MOCK else TwitterBot(cfg)

        # configure
        app.deps.twitter_bot = twitter_bot
        app.deps.twitter_bot.emergency = app.deps.emergency
        app.deps.broadcaster.channels = [
            ChannelDescriptor('twitter', '', Language.ENGLISH_TWITTER)
        ]
        r = await twitter_bot.verify_credentials()
        print(f'Verify: {r}')

        await asyncio.sleep(10)

        # await twitter_post_supply(app)

        # await twitter_bot.post('I want to make sure everything works.')
        # await twitter_post_price(app)


if __name__ == '__main__':
    asyncio.run(main())
