import typing

from localization.manager import BaseLocalization
from services.dialog.picture.nodes_pictures import NodePictureGenerator
from services.jobs.fetch.node_info import NodeInfoFetcher
from services.jobs.node_churn import NodeChurnDetector
from services.lib.cooldown import Cooldown
from services.lib.date_utils import HOUR, now_ts
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.draw_utils import img_to_bio
from services.lib.utils import WithLogger
from services.models.node_db import NodeStateDatabase
from services.models.node_info import NodeSetChanges, NetworkNodeIpInfo, NodeStatsItem
from services.models.time_series import TimeSeries
from services.notify.channel import BoardMessage


class NodeChurnNotifier(INotified, WithDelegates, WithLogger):
    STATS_RECORD_INTERVAL = 1 * HOUR

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

        self._min_changes_to_post_picture = deps.cfg.as_int('node_info.churn.min_changes_to_post_picture', 4)
        notify_cooldown = deps.cfg.as_interval('node_info.churn.cooldown', '10m')

        self._notify_cd = Cooldown(self.deps.db, 'NodeChurn:Notification', notify_cooldown, 10)
        self._record_metrics_cd = Cooldown(self.deps.db, 'NodeChurn:Metrics', self.STATS_RECORD_INTERVAL)

        self._node_stats_ts = TimeSeries('NodeMetrics', self.deps.db)

        self._db_before_churn = NodeStateDatabase(deps, 'NodeChurn:NodesBefore')
        self._db_after_churn = NodeStateDatabase(deps, 'NodeChurn:NodesAfter')

    MIGRATION = 'migration'

    async def on_data(self, sender, changes: NodeSetChanges):
        await self._record_statistics(changes)

        if changes.has_churn_happened:
            if changes.vault_migrating:
                await self._start_churn(changes)
            else:
                self.logger.warning('Churn without Vault migration!')
                await self._notify_when_node_churn_finished(changes)
        else:
            if not changes.vault_migrating:
                stage = await self.get_churning_stage()
                if stage == self.MIGRATION:
                    await self._finish_churn()
            else:
                self.logger.info(f'Other changes of the node set: {changes.count_of_changes} total')

    async def _start_churn(self, event: NodeSetChanges):
        self.logger.info('Start Node Churn!')
        await self._notify_when_node_churn_started(event)
        await self._set_last_churn_start_ts()
        await self._persist_node_churn(event)

        stage = self.MIGRATION if event.vault_migrating else ''
        await self._set_churning_stage(stage)

    async def _finish_churn(self):
        self.logger.info('Finish Node Churn!')
        event = await self._retrieve_node_churn()
        last_churn_ts = await self.get_last_churn_start_ts()
        if last_churn_ts:
            event.churn_duration = now_ts() - last_churn_ts
        await self._set_churning_stage('')
        await self._notify_when_node_churn_finished(event)

    async def _notify_when_node_churn_started(self, changes: NodeSetChanges):
        if await self._notify_cd.can_do():
            await self._notify_cd.do()

            await self.deps.broadcaster.notify_preconfigured_channels(
                BaseLocalization.notification_churn_started,
                changes
            )

    async def _notify_when_node_churn_finished(self, changes: NodeSetChanges):
        if not await self._notify_cd.can_do():
            return

        await self._notify_cd.do()

        # TEXT
        await self.deps.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_for_node_churn,
            changes)

        # PICTURE
        node_fetcher = NodeInfoFetcher(self.deps)
        result_network_info = await node_fetcher.get_node_list_and_geo_info(node_list=changes.nodes_all)

        async def node_div_pic_gen(loc: BaseLocalization):
            chart_pts = await NodeChurnNotifier(self.deps).load_last_statistics(NodePictureGenerator.CHART_PERIOD)
            gen = NodePictureGenerator(result_network_info, chart_pts, loc)
            pic = await gen.generate()
            bio_graph = img_to_bio(pic, gen.proper_name())
            caption = loc.PIC_NODE_DIVERSITY_BY_PROVIDER_CAPTION
            return BoardMessage.make_photo(bio_graph, caption)

        if changes.count_of_changes >= self._min_changes_to_post_picture:
            await self.deps.broadcaster.notify_preconfigured_channels(node_div_pic_gen)

    # ---- Various DB interactions ----

    DB_KEY_CHURN_START_TS = 'NodeChurn:LastChurnTS'
    DB_KEY_CHURN_STAGE = 'NodeChurn:Stage'

    async def _set_last_churn_start_ts(self):
        await self.deps.db.redis.set(self.DB_KEY_CHURN_START_TS, now_ts())

    async def get_last_churn_start_ts(self):
        v = await self.deps.db.redis.get(self.DB_KEY_CHURN_START_TS)
        return float(v) or None

    async def _set_churning_stage(self, stage):
        await self.deps.db.redis.set(self.DB_KEY_CHURN_STAGE, stage)

    async def get_churning_stage(self):
        r = await self.deps.db.redis.get(self.DB_KEY_CHURN_STAGE)
        return r or ''

    async def _persist_node_churn(self, change: NodeSetChanges):
        if change.has_churn_happened:
            await self._db_before_churn.save_node_info_list(change.nodes_previous)
            await self._db_after_churn.save_node_info_list(change.nodes_all)

    async def _retrieve_node_churn(self):
        prev_nodes = await self._db_before_churn.get_last_node_info_list()
        curr_nodes = await self._db_after_churn.get_last_node_info_list()
        if not prev_nodes or not curr_nodes:
            return

        changes = NodeChurnDetector.extract_changes(curr_nodes, prev_nodes)
        return changes

    async def _record_statistics(self, changes: NodeSetChanges):
        if not await self._record_metrics_cd.can_do():
            return

        node_set = NetworkNodeIpInfo(changes.nodes_all)

        active_nodes = node_set.active_nodes
        n_active_nodes = len(active_nodes)
        n_nodes = len(node_set.node_info_list)
        bond_min, bond_med, bond_max, bond_active_total = node_set.get_min_median_max_total_bond(active_nodes)
        bond_total = sum(n.bond for n in node_set.node_info_list)

        await self._node_stats_ts.add(
            bond_min=bond_min,
            bond_med=bond_med,
            bond_max=bond_max,
            bond_active_total=bond_active_total,
            bond_total=bond_total,
            n_nodes=n_nodes,
            n_active_nodes=n_active_nodes,
        )

        await self._record_metrics_cd.do()

    async def load_last_statistics(self, period_sec) -> typing.List[NodeStatsItem]:
        points = await self._node_stats_ts.get_last_values(period_sec, key=None, with_ts=True)
        return [NodeStatsItem.from_json(p) for p in points]
