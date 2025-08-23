import json
from collections import defaultdict
from contextlib import suppress

from comm.localization.eng_base import BaseLocalization
from lib.date_utils import now_ts
from lib.db import DB
from lib.depcont import DepContainer
from models.node_info import NodeSetChanges, NodeInfo, EventNodeFeeChange, \
    NodeEvent, NodeEventType, EventProviderBondChange, EventProviderStatus
from models.node_watchers import UserWatchlist
from .base import BasePersonalNotifier


class BondWatchlist(UserWatchlist):
    def __init__(self, db: DB):
        super().__init__(db, 'BondProvider')


class PersonalBondProviderNotifier(BasePersonalNotifier):
    def __init__(self, deps: DepContainer):
        watcher = BondWatchlist(deps.db)
        super().__init__(deps, watcher, max_events_per_message=20)
        self.min_bond_delta_to_react = 1e-1
        self.log_events = False

    async def on_data(self, sender, data: NodeSetChanges):
        if not data.is_empty and self.log_events:
            self.logger.info(f'NodeSetChanges: {data.count_of_changes} changes')

        events = []
        addresses = set()

        handlers = [self._handle_churn_events, self._handle_fee_events, self._handle_bond_amount_events]
        for handler in handlers:
            try:
                # noinspection PyArgumentList
                this_addresses, this_events = await handler(data)
                if self.log_events and this_events:
                    for ev in this_events:
                        ev: NodeEvent
                        self.logger.info(f'Bond tools event: {ev}')

                addresses |= this_addresses
                events += this_events

            except Exception as e:
                self.logger.exception(f'Failed to handle exception {e!r} in {handler.__name__}.', stack_info=True)

        self.logger.info(f'Total: {len(events)} events affecting {len(addresses)} addresses')

        await self.group_and_send_messages(addresses, events)

    async def _handle_fee_events(self, data: NodeSetChanges):
        fee_events = list(self._extract_fee_changes(data))
        provider_addresses = self._collect_provider_addresses_from_events(fee_events)

        return provider_addresses, fee_events

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
                for bp in curr_node.bond_providers:
                    yield NodeEvent.new(
                        curr_node,
                        NodeEventType.FEE_CHANGE,
                        data=EventNodeFeeChange(bp.address, old_node.node_operator_fee, curr_node.node_operator_fee)
                    )

    DB_KEY_HMAP_NODE_STATUS_CHANGE_TS = 'NodeChurn:InOutTimestamp'

    async def _memorize_node_status_change_ts(self, node: NodeInfo, ts: float, status: str) -> (str, float):
        if node:
            old_status, old_ts = await self.get_node_status_change_ts(node.node_address)
            await self.deps.db.redis.hset(
                self.DB_KEY_HMAP_NODE_STATUS_CHANGE_TS,
                node.node_address,
                json.dumps({
                    "ts": ts,
                    "status": status
                })
            )
            return old_status, old_ts
        else:
            return None, 0

    async def get_node_status_change_ts(self, node_address: str) -> (str, float):
        with suppress(Exception):
            data = await self.deps.db.redis.hget(self.DB_KEY_HMAP_NODE_STATUS_CHANGE_TS, node_address)
            data = json.loads(data)
            return (
                str(data['status']),
                float(data['ts']),
            )

        return None, 0

    DB_KEY_BOND_PROVIDER_STATUS = 'BondProvider:BondTime'

    @staticmethod
    def bond_provider_status_hash_key(provider_address: str, node: str):
        return f'node[{node}]-provider[{provider_address}]'

    async def _memorize_bond_provider_ts(self, provider: str, node: str, ts: float, rune_bond: float) -> (float, float):
        old_rune_bond, old_ts = await self.get_bond_provider_bond_and_change_ts(provider, node)
        await self.deps.db.redis.hset(
            self.DB_KEY_HMAP_NODE_STATUS_CHANGE_TS,
            self.bond_provider_status_hash_key(provider, node),
            json.dumps({
                "bond": rune_bond,
                "ts": ts,
            })
        )
        return old_rune_bond, old_ts

    async def get_bond_provider_bond_and_change_ts(self, provider_address: str, node: str) -> (float, float):
        with suppress(Exception):
            data = await self.deps.db.redis.hget(self.DB_KEY_BOND_PROVIDER_STATUS,
                                                 self.bond_provider_status_hash_key(provider_address, node))
            data = json.loads(data)
            return (
                float(data['bond']),
                float(data['ts']),
            )
        return 0, 0

    async def _handle_churn_events(self, data: NodeSetChanges):
        events = []

        # Collect all event data to a list of tuples (node, type, is_in?, status_string)
        for node in data.nodes_removed:
            events.append((node, NodeEventType.PRESENCE, False, 'removed'))
        for node in data.nodes_added:
            events.append((node, NodeEventType.PRESENCE, True, 'added'))
        for node in data.nodes_activated:
            events.append((node, NodeEventType.CHURNING, True, 'churn_in'))
        for node in data.nodes_deactivated:
            events.append((node, NodeEventType.CHURNING, False, 'churn_out'))

        # For every node read old status and timestamp and write new status now
        now = now_ts()
        old_statuses = {}
        for node, ev_type, on, status in events:
            old_status, old_ts = await self._memorize_node_status_change_ts(node, now, status)
            old_statuses[node.node_address] = old_status, old_ts

        # Prepare NodeEvent for each bond provider for each node
        events = [
            NodeEvent.new(
                node, ev_type,
                EventProviderStatus(
                    bp.address, bp.rune_bond, appeared=on,
                    previous_status=old_statuses[node.node_address][0],
                    previous_ts=old_statuses[node.node_address][1],
                )
            )
            for node, ev_type, on, status in events
            for bp in node.bond_providers
        ]

        # Collect all Bond provider addresses from events
        addresses = self._collect_provider_addresses_from_events(events)
        return addresses, events

    async def _handle_bond_amount_events(self, data: NodeSetChanges):
        events = []
        addresses = set()

        just_churned = data.has_churn_happened

        now = now_ts()

        for node_address, (prev_node, curr_node) in data.prev_and_curr_node_map.items():
            prev_providers = {bp.address: bp for bp in prev_node.bond_providers}
            curr_providers = {bp.address: bp for bp in curr_node.bond_providers}
            prev_bp_addresses = set(prev_providers.keys())
            curr_bp_addresses = set(curr_providers.keys())

            # Bond changes
            common_bp = prev_bp_addresses & curr_bp_addresses
            for provider in common_bp:
                curr_bond = curr_providers[provider].rune_bond
                prev_bond = prev_providers[provider].rune_bond
                delta_bond = curr_bond - prev_bond
                if abs(delta_bond) > self.min_bond_delta_to_react:
                    addresses.add(provider)

                    old_bond, old_ts = await self._memorize_bond_provider_ts(provider, curr_node.node_address, now,
                                                                             curr_bond)
                    duration_sec = now - old_ts if old_ts else 0

                    events.append(NodeEvent.new(
                        curr_node, NodeEventType.BOND_CHANGE,
                        EventProviderBondChange(
                            provider, prev_bond, curr_bond, on_churn=just_churned,
                            duration_sec=duration_sec,
                        )
                    ))

            added_bp = curr_bp_addresses - prev_bp_addresses
            for bp_address in added_bp:
                events.append(NodeEvent.new(
                    curr_node, NodeEventType.BP_PRESENCE,
                    EventProviderStatus(bp_address, curr_providers[bp_address].rune_bond, appeared=True)
                ))
                addresses.add(bp_address)

            left_bp = prev_bp_addresses - curr_bp_addresses
            for bp_address in left_bp:
                events.append(NodeEvent.new(
                    curr_node, NodeEventType.BP_PRESENCE,
                    EventProviderStatus(bp_address, prev_providers[bp_address].rune_bond, appeared=False)
                ))
                addresses.add(bp_address)

        return addresses, events

    async def generate_message_text(self, loc: BaseLocalization, group, settings, user, user_watch_addy_list, name_map):
        # regroup events into a hierarchy: BP -> Node -> Event
        bp_to_node_to_event = defaultdict(lambda: defaultdict(list))
        usd_per_rune = await self.deps.pool_cache.get_usd_per_rune()
        for event in group:
            event: NodeEvent
            event = event._replace(usd_per_rune=usd_per_rune)  # fill Rune price
            bp_to_node_to_event[event.data.bond_provider][event.node.node_address].append(event)

        return loc.notification_text_bond_provider_alert(bp_to_node_to_event, name_map)

    def get_users_from_event(self, ev, address_to_user):
        return address_to_user.get(ev.data.bond_provider)
