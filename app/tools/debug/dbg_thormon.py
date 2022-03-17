import asyncio
import logging

import localization
from services.dialog.slack.slack_bot import SlackBot
from services.jobs.fetch.thormon import ThorMonWSSClient, ThorMonSolvencyFetcher
from tools.lib.lp_common import LpAppFramework


async def a_test_wss():
    logging.basicConfig(level=logging.DEBUG)
    client = ThorMonWSSClient('mainnet')
    await client.listen_forever()


async def a_test_solvency(lp_app: LpAppFramework):
    fetcher = ThorMonSolvencyFetcher(lp_app.deps)
    data = await fetcher.fetch()
    print(data)


async def a_test_slack_message(lp_app: LpAppFramework):
    slack = SlackBot(lp_app.deps.cfg, lp_app.deps.db)
    loc: localization.BaseLocalization = localization.LocalizationManager(lp_app.deps.cfg).default

    r = slack.convert_html_to_my_format('Test\n\nsecond line')
    print(r)


async def a_test_slack_image(lp_app: LpAppFramework):
    slack = SlackBot(lp_app.deps.cfg, lp_app.deps.db)

    await slack.send_message_to_channel('')


async def main():
    lp_app = LpAppFramework()
    async with lp_app:
        await a_test_slack_message(lp_app)
    # await test_solvency()
    # await test_wss()


if __name__ == '__main__':
    asyncio.run(main())
