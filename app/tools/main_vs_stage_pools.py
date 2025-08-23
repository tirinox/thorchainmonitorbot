import asyncio

from api.aionode.connector import ThorConnector
from api.aionode.env import STAGENET
from api.aionode.types import thor_to_float
from lib.money import pretty_dollar, pretty_money
from lib.texts import sep
from tools.lib.lp_common import LpAppFramework

STAGENET_NODE = "https://stagenet-thornode.ninerealms.com/"

async def main():
    app = LpAppFramework()
    async with app(brief=True):
        d = app.deps

        stagenet_thor = ThorConnector(STAGENET, d.session)

        stagenet_pools = await stagenet_thor.query_pools()

        ph = await d.pool_cache.get()

        for pool in stagenet_pools:
            sep(pool.asset)
            real_price = ph.get_asset_price_in_usd(pool.asset)
            s_runes = thor_to_float(pool.balance_rune)
            s_asset = thor_to_float(pool.balance_asset)
            print(f"Stagenet pool contains {pretty_money(s_runes)} sRUNE")
            print(f"Stagenet pool contains {pretty_money(s_asset)} Asset"
                  f" which is {pretty_dollar(s_asset * real_price) if real_price else 'N/A'}")
            print(f"Real price of {pool.asset}: {pretty_dollar(real_price)}")

            if real_price:
                s_rune_price = s_asset / s_runes * real_price
                print(f"sRune is {pretty_dollar(s_rune_price)}")





if __name__ == '__main__':
    asyncio.run(main())
