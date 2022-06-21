# balances and synths
import asyncio
import logging

from localization.manager import BaseLocalization
from services.lib.utils import sep
from tools.lib.lp_common import LpAppFramework

EXAMPLE = 'thorAddrWithSynths'


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:
        await lp_app.prepare(brief=True)
        address = EXAMPLE
        balances = await lp_app.deps.thor_connector.query_balance(address)

        text = BaseLocalization.text_balances(balances)
        sep()
        print(text)
        sep()


if __name__ == '__main__':
    asyncio.run(main())
