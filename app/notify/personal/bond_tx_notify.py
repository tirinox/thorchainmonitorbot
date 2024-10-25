from collections import defaultdict

from comm.localization.eng_base import BaseLocalization
from lib.db import DB
from lib.depcont import DepContainer
from models.node_info import NodeEvent
from models.node_watchers import UserWatchlist
from .base import BasePersonalNotifier


class BondWatchlist(UserWatchlist):
    def __init__(self, db: DB):
        super().__init__(db, 'BondProvider')


class PersonalBondTxNotifier(BasePersonalNotifier):
    def get_users_from_event(self, ev, address_to_user):
        # todo check
        return address_to_user.get(ev.data.bond_provider)

    def __init__(self, deps: DepContainer):
        # todo
        watcher = BondWatchlist(deps.db)
        super().__init__(deps, watcher, max_events_per_message=20)

    async def on_data(self, sender, data):
        events = []
        addresses = set()
        # todo
        await self.group_and_send_messages(addresses, events)

    async def generate_message_text(self, loc: BaseLocalization, group, settings, user, user_watch_addy_list, name_map):
        # regroup events into a hierarchy: BP -> Node -> Event
        bp_to_node_to_event = defaultdict(lambda: defaultdict(list))
        for event in group:
            event: NodeEvent
            bp_to_node_to_event[event.data.bond_provider][event.node.node_address].append(event)

        return loc.notification_text_bond_provider_alert(bp_to_node_to_event, name_map)
