from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.models.node_info import NodeSetChanges, NodeInfo, EventNodeFeeChange, \
    NodeEvent, NodeEventType, EventProviderBondChange, EventProviderPresence
from services.models.node_watchers import UserWatchlist
from services.notify.personal.base import BasePersonalNotifier


class BondWatchlist(UserWatchlist):
    def __init__(self, db: DB):
        super().__init__(db, 'BondProvider')


class PersonalBondProviderNotifier(BasePersonalNotifier):
    def __init__(self, deps: DepContainer):
        watcher = BondWatchlist(deps.db)
        super().__init__(deps, watcher)
        self.min_bond_delta_to_react = 1e-6

        """
        Notifications:
        1) Your node churned in/out
        2) Your address appears on the node's list, (or disappears)
        3) Payout? bond changes (Rune amount, % to node, % APR, time in node)
        4) Your node changes percent of fee 
        """

    async def on_data(self, sender, data: NodeSetChanges):
        await self._handle_fee_events(data)
        await self._handle_churn_events(data)
        await self._handle_bond_amount_events(data)

    async def _handle_fee_events(self, data: NodeSetChanges):
        fee_events = list(self._extract_fee_changes(data))
        provider_addresses = self._collect_provider_addresses_from_events(fee_events)
        await self.group_and_send_messages(provider_addresses, fee_events)

    @staticmethod
    def _collect_provider_addresses_from_events(events):
        return set(
            provider.address for ev in events for provider in ev.node.bond_providers
        )

    @staticmethod
    def _extract_fee_changes(data: NodeSetChanges):
        pairs = data.prev_and_curr_node_map
        for address, (old_node, curr_node) in pairs.items():
            old_node: NodeInfo
            curr_node: NodeInfo
            if old_node.node_operator_fee != curr_node.node_operator_fee:
                yield NodeEvent(
                    curr_node.node_address,
                    NodeEventType.FEE_CHANGE,
                    data=EventNodeFeeChange(old_node.node_operator_fee, curr_node.node_operator_fee),
                    node=curr_node
                )

    async def _handle_churn_events(self, data: NodeSetChanges):
        events = []
        for node in data.nodes_removed:
            events.append((node, NodeEventType.PRESENCE, False))
        for node in data.nodes_added:
            events.append((node, NodeEventType.PRESENCE, True))
        for node in data.nodes_activated:
            events.append((node, NodeEventType.CHURNING, True))
        for node in data.nodes_deactivated:
            events.append((node, NodeEventType.CHURNING, False))
        events = [NodeEvent(node.node_address, ev_type, data) for node, ev_type, data in events]

        addresses = self._collect_provider_addresses_from_events(events)
        await self.group_and_send_messages(addresses, events)

    async def _handle_bond_amount_events(self, data: NodeSetChanges):
        events = []
        addresses = set()

        just_churned = data.has_churn_happened

        for node_address, (prev_node, curr_node) in data.prev_and_curr_node_map.items():
            prev_providers = {bp.address: bp for bp in prev_node.bond_providers}
            curr_providers = {bp.address: bp for bp in curr_node.bond_providers}
            prev_bp_addresses = set(prev_providers.keys())
            curr_bp_addresses = set(curr_providers.keys())

            # Bond changes
            common_bp = prev_bp_addresses & curr_bp_addresses
            for provider in common_bp:
                prev_bond = curr_providers[provider].rune_bond
                curr_bond = prev_providers[provider].rune_bond
                delta_bond = curr_bond - prev_bond
                if abs(delta_bond) > self.min_bond_delta_to_react:
                    addresses.add(provider)

                    events.append(NodeEvent(
                        node_address, NodeEventType.BOND_CHANGE,
                        EventProviderBondChange(
                            provider, prev_bond, curr_bond, on_churn=just_churned
                        )
                    ))

            added_bp = curr_bp_addresses - prev_bp_addresses
            for address in added_bp:
                events.append(NodeEvent(
                    node_address, NodeEventType.BP_PRESENCE,
                    EventProviderPresence(address, curr_providers[address].rune_bond, appeared=True)
                ))

            left_bp = prev_bp_addresses - curr_bp_addresses
            for address in left_bp:
                events.append(NodeEvent(
                    node_address, NodeEventType.BP_PRESENCE,
                    EventProviderPresence(address, prev_providers[address].rune_bond, appeared=False)
                ))

        await self.group_and_send_messages(addresses, events)

    async def filter_events(self, event_list, user, settings):
        return True  # all events are suitable

    async def generate_messages(self, loc, group, settings, user, user_watch_addy_list, name_map):
        messages = []
        for event in group:
            event: NodeEvent
            if event.type == NodeEventType.FEE_CHANGE:
                # todo!
                text = f'Fee changed for node: {event.address}: {event.data.previous} => {event.data.current}'
            elif event.type == NodeEventType.CHURNING:
                # todo!
                text = f'todo...'
            elif event.type == NodeEventType.BOND_CHANGE:
                # todo!
                text = f'todo...'
            elif event.type == NodeEventType.BP_PRESENCE:
                # todo!
                text = f'todo...'
            else:
                self.logger.warning(f'Unknown event type to build the alert text: {event.type}')
                continue

            messages.append(text)

        return messages
