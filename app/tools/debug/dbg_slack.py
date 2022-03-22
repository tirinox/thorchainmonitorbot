import asyncio

from services.dialog.picture.price_picture import price_graph_from_db
from services.dialog.slack.slack_bot import SlackBot
from services.lib.date_utils import DAY
from tools.lib.lp_common import LpAppFramework


async def a_test_slack(lp_app: LpAppFramework):
    deps = lp_app.deps
    slack = SlackBot(deps.cfg, deps.db)

    loc = deps.loc_man.default
    graph = await price_graph_from_db(deps.db, loc, period=14 * DAY)

    await slack.send_message_to_channel('C02L2AVS937', 'How are you?', picture=graph, pic_name='price.png')


async def main():
    lp_app = LpAppFramework()
    await a_test_slack(lp_app)
    await asyncio.sleep(5.0)


if __name__ == '__main__':
    asyncio.run(main())
