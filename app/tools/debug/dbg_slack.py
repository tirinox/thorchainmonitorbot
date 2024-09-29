import asyncio

from dialog.picture.price_picture import price_graph_from_db
from comm.dialog.slack.slack_bot import SlackBot
from lib.date_utils import DAY
from lib.texts import sep
from tools.lib.lp_common import LpAppFramework


async def a_test_slack_price(lp_app: LpAppFramework):
    deps = lp_app.deps
    slack = SlackBot(deps.cfg, deps.db, lp_app.deps.settings_manager)

    loc = deps.loc_man.default
    graph, graph_name = await price_graph_from_db(deps, loc, period=14 * DAY)

    await slack.send_message_to_channel('C02L2AVS937', 'How are you?', picture=graph, pic_name=graph_name)


async def a_test_slack_periodic_message(lp_app: LpAppFramework):
    deps = lp_app.deps
    slack = SlackBot(deps.cfg, deps.db, lp_app.deps.settings_manager)

    chan = 'D032VQSEBU2'
    # chan = 'C02L7H4H27N'

    while True:
        sep()
        await slack.send_message_to_channel(chan, 'How are you?')
        await asyncio.sleep(10.0)


async def main():
    lp_app = LpAppFramework()
    await a_test_slack_price(lp_app)
    # await lp_app.deps.db.get_redis()
    # await a_test_slack_periodic_message(lp_app)


if __name__ == '__main__':
    asyncio.run(main())
