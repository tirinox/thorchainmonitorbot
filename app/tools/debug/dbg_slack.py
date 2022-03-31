import asyncio

from services.dialog.picture.price_picture import price_graph_from_db
from services.dialog.slack.slack_bot import SlackBot
from services.lib.date_utils import DAY
from services.lib.utils import sep
from tools.lib.lp_common import LpAppFramework


async def a_test_slack_price(lp_app: LpAppFramework):
    deps = lp_app.deps
    slack = SlackBot(deps.cfg, deps.db)

    loc = deps.loc_man.default
    graph = await price_graph_from_db(deps.db, loc, period=14 * DAY)

    await slack.send_message_to_channel('C02L2AVS937', 'How are you?', picture=graph, pic_name='price.png')


async def a_test_slack_periodic_message(lp_app: LpAppFramework):
    deps = lp_app.deps
    slack = SlackBot(deps.cfg, deps.db)

    chan = 'D032VQSEBU2'
    # chan = 'C02L7H4H27N'

    while True:
        sep()
        await slack.send_message_to_channel(chan, 'How are you?')
        await asyncio.sleep(10.0)


async def main():
    lp_app = LpAppFramework()
    # await a_test_slack_price(lp_app)
    await lp_app.deps.db.get_redis()
    await a_test_slack_periodic_message(lp_app)


if __name__ == '__main__':
    asyncio.run(main())
