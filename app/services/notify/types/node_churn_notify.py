import typing

from localization.manager import BaseLocalization
from services.dialog.picture.nodes_pictures import NodePictureGenerator
from services.jobs.fetch.node_info import NodeInfoFetcher
from services.lib.cooldown import Cooldown
from services.lib.date_utils import DAY
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.draw_utils import img_to_bio
from services.lib.utils import WithLogger
from services.models.node_info import NodeSetChanges, NetworkNodeIpInfo, NodeStatsItem
from services.models.time_series import TimeSeries
from services.notify.channel import BoardMessage


class NodeChurnNotifier(INotified, WithDelegates, WithLogger):
    STATS_RECORD_INTERVAL = DAY

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

        self._min_changes_to_post_picture = deps.cfg.as_int('node_info.churn.min_changes_to_post_picture', 4)
        self._filter_nonsense = deps.cfg.get_pure('node_info.churn.filter_nonsense', True)
        notify_cooldown = deps.cfg.as_interval('node_info.churn.cooldown', '10m')

        self._notify_cd = Cooldown(self.deps.db, 'NodeChurn:Notification', notify_cooldown, 5)
        self._record_metrics_cd = Cooldown(self.deps.db, 'NodeChurn:Metrics', self.STATS_RECORD_INTERVAL)

        self._node_stats_ts = TimeSeries('NodeMetrics', self.deps.db)

    async def on_data(self, sender, changes: NodeSetChanges):
        await self._record_statistics(changes)

        if changes.is_empty:
            return

        if self._filter_nonsense and not changes.has_churn_happened:
            self.logger.warning(f'Node changes are insignificant: {changes} Ignore.')
            return

        if await self._notify_cd.can_do():
            await self._notify_cd.do()
            await self._notify_when_node_churn(changes)
            await self.pass_data_to_listeners(changes)

    async def _notify_when_node_churn(self, changes: NodeSetChanges):
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
