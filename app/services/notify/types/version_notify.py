from typing import List, NamedTuple

from redis.asyncio import Redis
from semver import VersionInfo

from services.lib.config import SubConfig
from services.lib.cooldown import Cooldown
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.node_info import NodeSetChanges, ZERO_VERSION
from services.models.version import AlertVersionChanged, AlertVersionUpgradeProgress


class KnownVersionStorage(WithLogger):
    def __init__(self, deps: DepContainer, context_name):
        super().__init__()
        self.deps = deps
        self.context_name = context_name

    DB_KEY_NEW_VERSION = 'THORNode.Version.Already.Notified.As.New'
    DB_KEY_LAST_PROGRESS = 'THORNode.Version.Last.Progress'

    async def is_version_known(self, new_v):
        r = await self.deps.db.get_redis()
        result = await r.sismember(self.DB_KEY_NEW_VERSION + self.context_name, str(new_v))
        return bool(result)

    async def mark_as_known(self, versions):
        r = await self.deps.db.get_redis()
        for v in versions:
            await r.sadd(self.DB_KEY_NEW_VERSION + self.context_name, str(v))

    async def get_upgrade_progress(self):
        r: Redis = await self.deps.db.get_redis()
        old_progress_raw = await r.get(self.DB_KEY_LAST_PROGRESS + self.context_name)
        try:
            return float(old_progress_raw)
        except (TypeError, ValueError):
            return 0.0

    async def set_upgrade_progress(self, progress: float):
        r: Redis = await self.deps.db.get_redis()
        await r.set(self.DB_KEY_LAST_PROGRESS + self.context_name, progress)


class VersionNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.store = KnownVersionStorage(deps, context_name='public')

        cfg: SubConfig = deps.cfg.node_info.version

        self.is_version_activation_enabled = bool(cfg.get('version_activates.enabled', True))
        cd_activate_sec = parse_timespan_to_seconds(str(cfg.get('version_activates.cooldown', '1h')))
        self.cd_activate_version = Cooldown(deps.db, 'activate_version', cd_activate_sec)

        self.is_new_version_enabled = bool(cfg.get('new_version_appears.enabled', True))
        cd_new_ver_sec = parse_timespan_to_seconds(str(cfg.get('new_version_appears.cooldown', '1h')))
        self.cd_new_version = Cooldown(deps.db, 'new_version', cd_new_ver_sec)

        self.is_upgrade_progress_enabled = bool(cfg.get('upgrade_progress.enabled', True))
        cd_upgrade_progress_sec = parse_timespan_to_seconds(str(cfg.get('upgrade_progress.cooldown', '2h')))
        self.cd_upgrade = Cooldown(deps.db, 'upgrade_progress', cd_upgrade_progress_sec)

        self.min_nodes_for_upgrade = cfg.as_int('upgrade_progress.minimum_nodes', 1)
        self.min_step_for_upgrade = cfg.as_int('upgrade_progress.minimum_progress_step_percent', 5) * 0.01

    async def _find_new_versions(self, data: NodeSetChanges) -> List[VersionInfo]:
        new_versions = data.version_set(data.nodes_all)
        if not new_versions:
            return []

        # filter out known ones
        versions_to_announce = []
        for new_v in new_versions:
            if not await self.store.is_version_known(new_v):
                n_nodes = data.count_version(data.nodes_all, new_v)
                if n_nodes >= self.min_nodes_for_upgrade:
                    versions_to_announce.append(new_v)

        return versions_to_announce

    @staticmethod
    def _test_active_version_changed(data: NodeSetChanges):
        previous_active_version = data.minimal_active_version(data.previous_active_only_nodes)
        current_active_version = data.current_active_version
        if previous_active_version != ZERO_VERSION and current_active_version != ZERO_VERSION:
            if previous_active_version != current_active_version:
                return previous_active_version, current_active_version

        return None, None  # no change

    async def _handle_new_versions(self, data: NodeSetChanges):
        if not await self.cd_new_version.can_do():
            return

        new_versions = await self._find_new_versions(data)

        if new_versions:
            await self.pass_data_to_listeners(
                AlertVersionChanged(
                    data,
                    new_versions,
                    None, None
                )
            )

            await self.store.mark_as_known(new_versions)
            await self.cd_new_version.do()

    async def _handle_active_version_change(self, data: NodeSetChanges):
        old_active_ver, new_active_ver = self._test_active_version_changed(data)

        if old_active_ver != new_active_ver:
            await self.pass_data_to_listeners(
                AlertVersionChanged(
                    data, [],
                    old_active_ver,
                    new_active_ver
                )
            )
            await self.cd_activate_version.do()

    async def _handle_upgrade_progress(self, data: NodeSetChanges):
        ver_con = data.version_consensus
        if not ver_con:
            return

        if ver_con.ratio == 1.0:
            return  # not interfere with _handle_active_version_change when progress == 100%!

        old_progress = await self.store.get_upgrade_progress()

        if abs(old_progress - ver_con.ratio) < self.min_step_for_upgrade:
            return  # no change

        more_than_min = ver_con.top_version_count >= self.min_nodes_for_upgrade

        if more_than_min and await self.cd_upgrade.can_do():
            await self.cd_upgrade.do()
            await self.store.set_upgrade_progress(ver_con.ratio)
            await self.pass_data_to_listeners(AlertVersionUpgradeProgress(data, ver_con))

    async def on_data(self, sender, changes: NodeSetChanges):
        if self.is_new_version_enabled:
            await self._handle_new_versions(changes)

        if self.is_version_activation_enabled:
            await self._handle_upgrade_progress(changes)

        if self.is_version_activation_enabled:
            await self._handle_active_version_change(changes)
