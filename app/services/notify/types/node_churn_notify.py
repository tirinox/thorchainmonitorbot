from localization import BaseLocalization
from services.dialog.picture.node_geo_picture import node_geo_pic
from services.jobs.fetch.base import INotified
from services.jobs.fetch.node_info import NodeInfoFetcher
from services.lib.cooldown import Cooldown
from services.lib.date_utils import MINUTE
from services.lib.depcont import DepContainer
from services.lib.draw_utils import img_to_bio
from services.notify.channel import BoardMessage
from services.lib.utils import class_logger
from services.models.node_info import NodeSetChanges


class NodeChurnNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)
        self._filter_nonsense = deps.cfg.get_pure('node_info.churn.filter_nonsense', True)
        self.cd = Cooldown(self.deps.db, 'NodeChurnNotification', MINUTE * 10, 5)

    async def on_data(self, sender, changes: NodeSetChanges):
        if changes.is_empty:
            return

        if self._filter_nonsense and changes.is_nonsense:
            self.logger.warning(f'Node changes is nonsense! {changes}')
            return

        if await self.cd.can_do():
            await self._notify_when_node_churn(changes)
            await self.cd.do()

    async def _notify_when_node_churn(self, changes: NodeSetChanges):
        # TEXT
        await self.deps.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_for_node_churn,
            changes)

        # PICTURE
        node_fetcher = NodeInfoFetcher(self.deps)
        result_network_info = await node_fetcher.get_node_list_and_geo_info(node_list=changes.nodes_all)

        async def node_div_pic_gen(loc: BaseLocalization):
            graph = await node_geo_pic(result_network_info, loc)
            bio_graph = img_to_bio(graph, "node_diversity.png")
            return BoardMessage.make_photo(bio_graph)

        if changes.count_of_changes > 2:  # todo: put it to config
            await self.deps.broadcaster.notify_preconfigured_channels(node_div_pic_gen)
