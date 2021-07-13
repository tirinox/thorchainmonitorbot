import asyncio
import logging
import random
from copy import copy

from semver import VersionInfo

from localization import LocalizationManager
from services.jobs.fetch.node_info import NodeInfoFetcher
from services.lib.utils import setup_logs, sep
from services.models.node_info import NodeSetChanges
from tools.lib.lp_common import LpAppFramework


async def node_version_notification_check_1(lpgen: LpAppFramework, data):
    loc_man: LocalizationManager = lpgen.deps.loc_man
    loc_ru = loc_man.get_from_lang('rus')
    loc_en = loc_man.get_from_lang('eng')

    for loc in (loc_ru, loc_en):
        sep()
        msg = loc.notification_text_version_upgrade(
            data,
            new_versions=[
                VersionInfo.parse('0.59.1'),
                VersionInfo.parse('0.60.0'),
            ],
            old_active_ver=VersionInfo.parse('0.59.1'),
            # new_active_ver=VersionInfo.parse('0.45.0')
            new_active_ver=VersionInfo.parse('0.59.2')
        )
        print(msg)
        await lpgen.send_test_tg_message(msg)

    await lpgen.send_test_tg_message('-----')

    data: NodeSetChanges = copy(data)
    for n in data.nodes_all:
        if random.uniform(0, 1) > 0.5:
            n.version = '0.59.2'
        if random.uniform(0, 1) > 0.5:
            n.version = '0.60.0'
        if random.uniform(0, 1) > 0.5:
            n.version = '0.60.1'
        if random.uniform(0, 1) > 0.5:
            n.version = '0.60.3'

    for loc in (loc_ru, loc_en):
        sep()
        msg = loc.notification_text_version_upgrade(
            data,
            new_versions=[],
            old_active_ver=VersionInfo.parse('0.59.1'),
            # new_active_ver=VersionInfo.parse('0.45.0')
            new_active_ver=VersionInfo.parse('0.59.2')
        )
        print(msg)
        await lpgen.send_test_tg_message(msg)


async def main():
    lpgen = LpAppFramework()
    async with lpgen:
        node_info_fetcher = NodeInfoFetcher(lpgen.deps)

        data = await node_info_fetcher.fetch()

        await node_version_notification_check_1(lpgen, data)


if __name__ == "__main__":
    setup_logs(logging.INFO)
    asyncio.run(main())
