import asyncio
import random
from typing import List

from semver import VersionInfo

from comm.localization.eng_base import BaseLocalization
from jobs.fetch.node_info import NodeInfoFetcher
from jobs.node_churn import NodeChurnDetector
from lib.depcont import DepContainer
from models.node_info import NodeInfo
from notify.public.version_notify import VersionNotifier
from tools.lib.lp_common import LpAppFramework


class DbgVersion:
    def __init__(self, app: LpAppFramework):
        self.app = app
        self.deps = app.deps

    async def dbg_notify(self, changes):
        await self.deps.broadcaster.broadcast_to_all(
            "debug:version",
            BaseLocalization.notification_text_version_changed,
            changes,
            [VersionInfo.parse('1.90.2')],
            None, None
        )

        await self.deps.broadcaster.broadcast_to_all(
            "debug:version",
            BaseLocalization.notification_text_version_changed,
            changes, [],
            VersionInfo.parse('1.90.4'),
            VersionInfo.parse('1.90.5')
        )

        await self.deps.broadcaster.broadcast_to_all(
            "debug:version",
            BaseLocalization.notification_text_version_changed_progress,
            changes, changes.version_consensus
        )


class DbgNodeFetcherMockVersionAdoption(NodeInfoFetcher):
    def __init__(self, deps: DepContainer, new_version):
        super().__init__(deps)
        self.new_version = new_version
        self.nodes_infected = set()
        self.sleep_period = 10
        self.initial_sleep = 0

    async def fetch(self) -> List[NodeInfo]:
        results = await super().fetch()

        random.shuffle(results)

        new_infected = False
        for node in results:
            if node.is_active:
                if node.node_address in self.nodes_infected:
                    node.version = str(self.new_version)
                elif not new_infected:
                    new_infected = True
                    print(f'Infected node {node.node_address}: {node.version} -> {self.new_version}')
                    node.version = str(self.new_version)
                    self.nodes_infected.add(node.node_address)
                    print(f'Total infected nodes: {len(self.nodes_infected)}')

        for node in results:
            if node.version == self.new_version:
                print(f'Found node with new version {node.node_address}: {node.version}')

        return results


async def main():
    app = LpAppFramework()
    async with app:
        # dbg = DbgVersion(app)
        # changes = NodeSetChanges()
        # await dbg.dbg_notify(changes)

        d = app.deps
        fetcher = DbgNodeFetcherMockVersionAdoption(d, VersionInfo.parse('1.267.13'))

        churn_detector = NodeChurnDetector(d)
        fetcher.add_subscriber(churn_detector)

        notifier_version = VersionNotifier(d)
        churn_detector.add_subscriber(notifier_version)

        await fetcher.run()


if __name__ == "__main__":
    asyncio.run(main())
