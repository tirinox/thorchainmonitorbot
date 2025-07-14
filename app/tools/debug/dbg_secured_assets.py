import asyncio
import json

from jobs.fetch.secured_asset import SecuredAssetAssetFetcher
from lib.money import pretty_dollar
from lib.texts import sep
from lib.utils import namedtuple_to_dict
from tools.lib.lp_common import LpAppFramework


async def dbg_fetch_secured_assets(app):
    f = SecuredAssetAssetFetcher(app.deps)


    # v_prev, v_curr = await f.load_volumes_usd_prev_curr("BTC.BTC", days=1)
    # sep("PREV")
    # print(v_prev)
    # sep("CURR")
    # print(v_curr)
    # return

    # h = await f.load_holders('xrp-xrp')
    # print(f"XRP holders: {h}")

    secured_asset_info = await f.fetch()

    sep()
    print("Secured Assets Fetch:")
    print(f"total_pool_usd = {pretty_dollar(secured_asset_info.total_pool_usd)}")
    print(f"total_vault_usd = {pretty_dollar(secured_asset_info.total_vault_usd)}")
    for asset in secured_asset_info.assets:
        sep(asset.asset)
        print(asset)

    sep()
    raw = namedtuple_to_dict(secured_asset_info)
    print(json.dumps(raw, indent=2))


async def dbg_fetch_secured_volumes(app):
    ...


async def run():
    app = LpAppFramework(log_level='INFO')
    async with app(brief=True):
        await app.deps.pool_fetcher.run_once()
        await dbg_fetch_secured_assets(app)


if __name__ == '__main__':
    asyncio.run(run())
