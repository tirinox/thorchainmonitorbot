from collections import defaultdict, Counter
from typing import Optional, List

from lib.config import SubConfig
from lib.constants import Chains
from lib.date_utils import parse_timespan_to_seconds, HOUR
from lib.depcont import DepContainer
from lib.texts import sep
from lib.utils import most_common, estimate_max_by_committee
from models.node_info import NodeEvent, NodeEventType, EventBlockHeight, NodeInfo
from .helpers import BaseChangeTracker, NodeOpSetting
from .user_data import UserDataCache


class ChainHeightTracker(BaseChangeTracker):
    METHOD_MOST_COMMON = 'most_common'
    METHOD_MAXIMUM = 'max'
    METHOD_MAX_COMMITTEE = 'max_committee'

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.block_times = dict(deps.cfg.get_pure('blockchain.block_time', {}))
        for chain, en_time in self.block_times.items():
            self.block_times[chain] = parse_timespan_to_seconds(en_time)

        self.recent_max_blocks = {}
        self.cache: Optional[UserDataCache] = None

        sub_cfg = deps.cfg.get('node_op_tools.types.chain_height', SubConfig({}))
        self.chain_height_method = sub_cfg.as_str('top_height_estimation_method', self.METHOD_MAX_COMMITTEE)
        self.min_committee = sub_cfg.as_int('min_committee_members', 3)
        self.debug = False
        self._first_tick = True

    def get_block_time(self, chain):
        return self.block_times.get(chain, Chains.block_time_default(chain))

    def blocks_to_lag(self, chain: str, seconds: float):
        return seconds / self.get_block_time(chain)

    @staticmethod
    def estimate_block_height_most_common(nodes: List[NodeInfo]):
        chain_block_height = defaultdict(list)
        for node in nodes:
            for name, height in node.chain_dict.items():
                if height > 0:
                    chain_block_height[name].append(height)

        return {chain: most_common(height_list) for chain, height_list in chain_block_height.items()}

    @staticmethod
    def estimate_block_height_maximum(nodes: List[NodeInfo]):
        chain_block_height = defaultdict(int)
        for node in nodes:
            for name, height in node.chain_dict.items():
                if height > 0:
                    chain_block_height[name] = max(chain_block_height[name], height)

        return chain_block_height

    @staticmethod
    def estimate_block_height_max_by_committee(nodes: List[NodeInfo], committee_members_min):
        chain_block_height = defaultdict(list)
        for node in nodes:
            for chain_name, chain_height in node.chain_dict.items():
                chain_height = int(chain_height)
                if chain_height:
                    chain_block_height[chain_name].append(chain_height)

        return {chain: estimate_max_by_committee(
            height_list,
            minimal_members=committee_members_min,
        ) for chain, height_list in chain_block_height.items()}

    @staticmethod
    def _add_thorchain_height(nodes: List[NodeInfo]):
        # add THOR Chain to the Chain List
        for node in nodes:
            if not node.observe_chains:
                node.observe_chains = []
            node.observe_chains.append({
                'chain': Chains.THOR,
                'height': node.active_block_height
            })
        return nodes

    def estimate_block_height(self, nodes: List[NodeInfo]):
        prev_last_blocks = self.recent_max_blocks
        method = self.chain_height_method

        nodes = self._add_thorchain_height(nodes)

        if method == self.METHOD_MAXIMUM:
            self.recent_max_blocks = self.estimate_block_height_maximum(nodes)
        elif method == self.METHOD_MOST_COMMON:
            self.recent_max_blocks = self.estimate_block_height_most_common(nodes)
        elif method == self.METHOD_MAX_COMMITTEE:
            self.recent_max_blocks = self.estimate_block_height_max_by_committee(
                nodes, committee_members_min=self.min_committee)
        else:
            raise ValueError(f'unknown method: {method}')

        if self.debug:
            sep()
            print('last height (!)', prev_last_blocks)
            print('got  height (!)', self.recent_max_blocks)
            print('max  height (!)', dict(self.estimate_block_height_maximum(nodes)))
            keys = list(sorted(prev_last_blocks.keys()))
            for k in keys:
                variants = (t.chain_dict.get(k).height for t in nodes if k in t.observe_chains)
                variants = Counter(variants)
                old_v = prev_last_blocks.get(k)
                new_v = self.recent_max_blocks.get(k)
                delta = new_v - old_v if isinstance(old_v, int) and isinstance(new_v, int) else 'N/A'
                print(f"{k}: {old_v} => {new_v}; delta = {delta}; variants = {variants}")
            sep()

    KEY_SYNC_STATE = 'sync'

    def get_user_state(self, user, node, service):
        return self.cache.user_node_service_data[user][node][service].get(self.KEY_SYNC_STATE, True)

    def set_user_state(self, user, node, service, is_ok):
        self.cache.user_node_service_data[user][node][service][self.KEY_SYNC_STATE] = is_ok

    async def get_events_unsafe(self) -> List[NodeEvent]:
        if self._first_tick:
            self._first_tick = False
            return []

        total_online, total_offline = 0, 0

        events = []
        for chain, expected_block_height in self.recent_max_blocks.items():
            for node in self.node_set_change.nodes_all:
                actual = node.chain_dict.get(chain)
                actual_block_height = actual or 0
                if actual_block_height == 0:
                    continue

                is_ok = actual_block_height >= expected_block_height
                time_lag = abs(actual_block_height - expected_block_height) * self.get_block_time(chain)

                if is_ok:
                    total_online += 1
                else:
                    total_offline += 1

                events.append(NodeEvent(
                    node.node_address, NodeEventType.BLOCK_HEIGHT,
                    EventBlockHeight(
                        chain, expected_block_height, actual_block_height,
                        time_lag, is_ok
                    ),
                    node=node, tracker=self
                ))

        total = total_offline + total_offline
        self.logger.info(f'Summary: {total_offline = }, {total_online = }, {total = } blockchain clients')

        return events

    @staticmethod
    def get_service_name(chain):
        return f'height_{chain}'

    async def is_event_ok(self, event: NodeEvent, user_id, settings: dict) -> bool:
        if not bool(settings.get(NodeOpSetting.CHAIN_HEIGHT_ON, True)):
            return False

        event_data: EventBlockHeight = event.data

        threshold_interval = float(settings.get(NodeOpSetting.CHAIN_HEIGHT_INTERVAL, HOUR))
        threshold_interval = max(threshold_interval, self.get_block_time(event_data.chain) * 1.5)

        node, service = event.node.node_address, self.get_service_name(event_data.chain)
        user_thinks_sync = self.get_user_state(user_id, node, service)

        if user_thinks_sync and not event_data.is_sync and event_data.how_long_behind >= threshold_interval:
            self.set_user_state(user_id, node, service, is_ok=False)
            return True

        if not user_thinks_sync and event_data.is_sync:
            self.set_user_state(user_id, node, service, is_ok=True)
            return True

        return False
