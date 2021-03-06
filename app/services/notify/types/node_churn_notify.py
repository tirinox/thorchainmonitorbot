import logging

from localization import BaseLocalization
from services.dialog.picture.node_geo_picture import node_geo_pic
from services.jobs.fetch.base import INotified
from services.jobs.fetch.node_info import NodeInfoFetcher
from services.lib.cooldown import Cooldown
from services.lib.date_utils import MINUTE
from services.lib.depcont import DepContainer
from services.lib.draw_utils import img_to_bio
from services.lib.texts import BoardMessage
from services.models.node_info import NodeInfoChanges, NodeInfo


class NodeChurnNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cd = Cooldown(self.deps.db, 'NodeChurnNotification', MINUTE * 10, 5)

    async def on_data(self, sender, data: NodeInfoChanges):
        if not data.is_empty and not data.is_nonsense:
            if await self.cd.can_do():
                await self._notify_when_node_churn(data)
                await self.cd.do()

    async def _notify_when_node_churn(self, changes: NodeInfoChanges):
        # TEXT
        await self.deps.broadcaster.notify_preconfigured_channels(self.deps.loc_man,
                                                                  BaseLocalization.notification_text_for_node_churn,
                                                                  changes)

        # PICTURE
        user_lang_map = self.deps.broadcaster.telegram_chats_from_config(self.deps.loc_man)

        node_fetcher = NodeInfoFetcher(self.deps)
        result_network_info = await node_fetcher.get_node_list_and_geo_info(node_list=changes.nodes_all)

        async def node_div_pic_gen(chat_id):
            loc: BaseLocalization = user_lang_map[chat_id]
            graph = await node_geo_pic(result_network_info, loc)
            bio_graph = img_to_bio(graph, "node_diversity.png")
            return BoardMessage.make_photo(bio_graph)

        if changes.count_of_changes > 2:
            await self.deps.broadcaster.broadcast(user_lang_map, node_div_pic_gen)
