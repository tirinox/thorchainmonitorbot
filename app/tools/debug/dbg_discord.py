import asyncio

from comm.localization.languages import Language
from comm.discord.discord_bot import DiscordBot
from notify.channel import ChannelDescriptor
from tools.lib.lp_common import LpAppFramework


async def debug_prepare_discord_bot(app: LpAppFramework):
    app.deps.discord_bot = DiscordBot(app.deps.cfg, None)
    app.deps.discord_bot.start_in_background()

    await asyncio.sleep(2.5)

    app.deps.broadcaster.channels = [
        ChannelDescriptor('discord', '918447226232139776', Language.ENGLISH)
    ]
    return app
