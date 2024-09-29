import asyncio
import logging

from notify.broadcast import Broadcaster
from notify.channel import ChannelDescriptor, BoardMessage, Messengers
from tools.lib.lp_common import LpAppFramework


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app(brief=True):
        # await my_test_circulating(lp_app)
        b: Broadcaster = lp_app.deps.broadcaster

        # adjust for testing conditions
        b._limit_number = 2
        b._limit_period = 10  # sec
        b._limit_cooldown = 10

        i = 1
        while True:
            outcome = await b.safe_send_message_rate(ChannelDescriptor(
                Messengers.TELEGRAM,
                "192398802",
                lang='rus'
            ), BoardMessage(
                f"☣️ This is spam message #{i}"
            ))

            print(f'#{i}: {outcome = }')

            i += 1
            await asyncio.sleep(0.8)


asyncio.run(main())
