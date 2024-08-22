import asyncio

from localization.eng_base import BaseLocalization
from services.jobs.fetch.chain_id import ChainIdFetcher, EventChainId, AlertChainIdChange
from services.lib.var_file import var_file_loop
from services.notify.types.chain_id_notify import ChainIdNotifier
from tools.lib.lp_common import LpAppFramework


async def demo_live_chain_id_changes(app: LpAppFramework):
    f = ChainIdFetcher(app.deps)
    data: EventChainId = await f.fetch()

    notifier = ChainIdNotifier(app.deps)
    notifier.add_subscriber(app.deps.alert_presenter)

    async def var_changed(_, curr):
        nonlocal data
        data = data._replace(chain_id=curr.get('net_id'))

    async def every_tick(var_file):
        await notifier.on_data(None, data)

    await var_file_loop(var_changed, every_tick, sleep_time=1.0)


async def demo_all_locs(app: LpAppFramework):
    await app.test_all_locs(BaseLocalization.notification_text_chain_id_changed, None,
                            AlertChainIdChange(
                                "thorchain-foo-v1",
                                "thorchain-bar-v2"
                            ))


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        # await demo_live_network_ident_changes(app)
        await demo_all_locs(app)


if __name__ == '__main__':
    asyncio.run(run())
