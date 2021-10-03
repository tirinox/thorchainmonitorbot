from collections import defaultdict
from typing import Optional

from services.lib.constants import Chains
from services.lib.date_utils import parse_timespan_to_seconds, HOUR
from services.lib.depcont import DepContainer
from services.lib.utils import most_common, estimate_max_by_committee
from services.models.node_info import NodeEvent, NodeEventType, EventBlockHeight
from services.models.thormon import ThorMonAnswer
from services.notify.personal.user_data import UserDataCache
from services.notify.personal.helpers import BaseChangeTracker, NodeOpSetting


class ChainHeightTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.block_times = dict(deps.cfg.get_pure('blockchain.block_time', {}))
        for chain, en_time in self.block_times.items():
            self.block_times[chain] = parse_timespan_to_seconds(en_time)

        self.recent_max_blocks = {}
        self.cache: Optional[UserDataCache] = None

    def get_block_time(self, chain):
        return self.block_times.get(chain, Chains.block_time_default(chain))

    def blocks_to_lag(self, chain: str, seconds: float):
        return seconds / self.get_block_time(chain)

    @staticmethod
    def estimate_block_height_most_common(data: ThorMonAnswer):
        chain_block_height = defaultdict(list)
        for node in data.nodes:
            for name, chain_info in node.observe_chains.items():
                if chain_info.valid:
                    chain_block_height[name].append(chain_info.height)
            # chain_block_height[Chains.THOR].append(node.active_block_height) # todo!

        return {chain: most_common(height_list) for chain, height_list in chain_block_height.items()}

    @staticmethod
    def estimate_block_height_maximum(data: ThorMonAnswer):
        chain_block_height = defaultdict(int)
        for node in data.nodes:
            for name, chain_info in node.observe_chains.items():
                if chain_info.valid:
                    chain_block_height[name] = max(chain_block_height[name], chain_info.height)
            # chain_block_height[Chains.THOR].append(node.active_block_height) # todo!
        return chain_block_height

    @staticmethod
    def estimate_block_height_max_by_committee(data: ThorMonAnswer, committee_members_min):
        chain_block_height = defaultdict(list)
        for node in data.nodes:
            for name, chain_info in node.observe_chains.items():
                if chain_info.valid:
                    chain_block_height[name].append(chain_info.height)

        return {chain: estimate_max_by_committee(
            height_list,
            minimal_members=committee_members_min
        ) for chain, height_list in chain_block_height.items()}

    def estimate_block_height(self, data: ThorMonAnswer, method='max_committee'):
        if method == 'max':
            self.recent_max_blocks = self.estimate_block_height_maximum(data)
        elif method == 'most_common':
            self.recent_max_blocks = self.estimate_block_height_most_common(data)
        elif method == 'max_committee':
            self.recent_max_blocks = self.estimate_block_height_max_by_committee(data, committee_members_min=3)
        else:
            raise ValueError(f'unknown method: {method}')

        # # fixme: debug(!) ------ 8< -------
        # print('got height (!)', self.recent_max_blocks)  # fixme; debug (!)
        # print('max height (!)', self.estimate_block_height_maximum(data))
        # # fixme: debug(!) ------ 8< -------

    KEY_SYNC_STATE = 'sync'

    def get_user_state(self, user, node, service):
        return self.cache.user_node_service_data[user][node][service].get(self.KEY_SYNC_STATE, True)

    def set_user_state(self, user, node, service, is_ok):
        self.cache.user_node_service_data[user][node][service][self.KEY_SYNC_STATE] = is_ok

    async def get_events(self, last_answer: ThorMonAnswer, user_cache: UserDataCache):
        self.cache = user_cache

        events = []
        for chain, expected_block_height in self.recent_max_blocks.items():
            for node in last_answer.nodes:
                actual = node.observe_chains.get(chain)
                actual_block_height = actual.height if actual else 0
                if actual_block_height == 0:
                    continue

                is_ok = actual_block_height >= expected_block_height
                time_lag = abs(actual_block_height - expected_block_height) * self.get_block_time(chain)

                events.append(NodeEvent(
                    node.node_address, NodeEventType.BLOCK_HEIGHT,
                    EventBlockHeight(
                        chain, expected_block_height, actual_block_height,
                        time_lag, is_ok
                    ),
                    thor_node=node, tracker=self
                ))

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

        node, service = event.thor_node.node_address, self.get_service_name(event_data.chain)
        user_thinks_sync = self.get_user_state(user_id, node, service)

        if user_thinks_sync and not event_data.is_sync and event_data.how_long_behind >= threshold_interval:
            self.set_user_state(user_id, node, service, is_ok=False)
            return True

        if not user_thinks_sync and event_data.is_sync:
            self.set_user_state(user_id, node, service, is_ok=True)
            return True

        return False
