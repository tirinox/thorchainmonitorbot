import asyncio
import json

from jobs.fetch.cached.swap_history import SwapHistoryFetcher
from jobs.fetch.secured_asset import SecuredAssetAssetFetcher
from lib.money import pretty_dollar
from lib.texts import sep
from lib.utils import namedtuple_to_dict
from notify.channel import BoardMessage
from notify.public.secured_notify import SecureAssetSummaryNotifier
from tools.lib.lp_common import LpAppFramework

DEMO_DATA_FILENAME = "./renderer/demo/secured_asset_summary.json"


async def dbg_fetch_secured_assets(app):
    f = SecuredAssetAssetFetcher(app.deps)
    secured_asset_info = await f.fetch()

    sep()
    print("Secured Assets Fetch:")
    print(f"total_pool_usd = {pretty_dollar(secured_asset_info.current.total_pool_usd)}")
    print(f"total_vault_usd = {pretty_dollar(secured_asset_info.current.total_vault_usd)}")
    for asset in secured_asset_info.current.assets.values():
        sep(asset.asset)
        print(asset)

    sep()
    raw = namedtuple_to_dict(secured_asset_info)
    print(json.dumps(raw, indent=2))

    with open(DEMO_DATA_FILENAME, "r") as f:
        existing_data = json.load(f)

    existing_data["parameters"].update(raw)
    with open(DEMO_DATA_FILENAME, "w") as f:
        json.dump(existing_data, f, indent=2)


async def dbg_fetch_secured_volumes(app):
    f = SwapHistoryFetcher(app.deps.midgard_connector, 10)
    mdg = await f.get()
    sep("Swap History Fetch:")
    print(mdg)


async def dbg_send_picture_of_secured_assets(app):
    f = SecuredAssetAssetFetcher(app.deps)
    secured_asset_info = await f.fetch()
    app.deps.alert_presenter.renderer.dbg_log_full_requests = True
    img, img_name = await app.deps.alert_presenter.render_secured_asset_summary(None, secured_asset_info)
    await app.deps.broadcaster.broadcast_to_all(
        BoardMessage.make_photo(img, caption="Secured assets", photo_file_name=img_name)
    )


async def dbg_continuous_secured_assets(app):
    d = app.deps
    secured_asset_fetcher = SecuredAssetAssetFetcher(d)
    secured_asset_fetcher.sleep_period = 10.0
    secured_asset_notifier = SecureAssetSummaryNotifier(d)
    secured_asset_notifier.cd.cooldown = 0.0
    secured_asset_fetcher.add_subscriber(secured_asset_notifier)
    secured_asset_notifier.add_subscriber(d.alert_presenter)
    await secured_asset_fetcher.run()


async def run():
    app = LpAppFramework(log_level='DEBUG')
    async with app:
        # await dbg_fetch_secured_assets(app)
        # await dbg_fetch_secured_volumes(app)
        # await dbg_continuous_secured_assets(app)
        await dbg_send_picture_of_secured_assets(app)


if __name__ == '__main__':
    asyncio.run(run())
