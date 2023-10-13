import asyncio

from semver import VersionInfo

from localization.eng_base import BaseLocalization
from services.models.node_info import NodeSetChanges
from tools.lib.lp_common import LpAppFramework


class DbgVersion:
    def __init__(self, app: LpAppFramework):
        self.app = app
        self.deps = app.deps

    async def dbg_notify(self, changes):
        await self.deps.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_version_upgrade,
            changes,
            [VersionInfo.parse('1.90.2')],
            None, None
        )

        await self.deps.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_version_upgrade,
            changes, [],
            VersionInfo.parse('1.90.4'),
            VersionInfo.parse('1.90.5')
        )

        await self.deps.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_version_upgrade_progress,
            changes, changes.version_consensus
        )


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        dbg = DbgVersion(app)
        changes = NodeSetChanges()
        await dbg.dbg_notify(changes)


if __name__ == "__main__":
    asyncio.run(main())
