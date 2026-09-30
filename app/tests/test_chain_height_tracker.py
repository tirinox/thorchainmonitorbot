import logging
from types import SimpleNamespace

import pytest

from lib.config import Config
from lib.constants import Chains
from models.node_info import NodeInfo, NodeSetChanges, NodeEventType
from notify.personal.chain_height import ChainHeightTracker
from notify.personal.personal_main import NodeChangePersonalNotifier
from notify.personal.user_data import UserDataCache
from tests.fakes import FakeDB

USER = '42'
LAGGING = 'thor1lagging'
BTC_BLOCK = Chains.block_time_default(Chains.BTC)


def _node(address, btc_height, status=NodeInfo.ACTIVE):
    return NodeInfo(status=status, node_address=address, active_block_height=1_000 + len(address),
                    observe_chains=[{'chain': Chains.BTC, 'height': btc_height}])


def _nodes(lagging_height, top=1_000):
    return [_node(f'thor1node{i}', top) for i in range(3)] + [_node(LAGGING, lagging_height)]


class Ticker:
    def __init__(self):
        self.tracker = ChainHeightTracker(SimpleNamespace(cfg=Config(data={})))
        self.user_cache = UserDataCache.from_json(None)

    async def alerts(self, nodes):
        t = self.tracker
        t.estimate_block_height(nodes)
        t.node_set_change = NodeSetChanges(nodes_all=nodes, nodes_previous=nodes)
        t.user_cache = self.user_cache
        events = await t.get_events()
        return [e for e in events if await t.is_event_ok(e, USER, {})]


@pytest.mark.asyncio
async def test_lagging_node_alerts_once_and_then_when_it_catches_up():
    ticker = Ticker()
    assert await ticker.alerts(_nodes(900)) == []  # the first tick only learns the heights

    [ev] = await ticker.alerts(_nodes(900))  # 100 BTC blocks behind, far over the default 1 hour
    assert ev.type == NodeEventType.BLOCK_HEIGHT and ev.address == LAGGING
    assert not ev.data.is_sync and ev.data.block_lag == 100
    assert ev.data.how_long_behind == pytest.approx(100 * BTC_BLOCK)

    assert await ticker.alerts(_nodes(905)) == []  # still behind: no repeat

    [ev] = await ticker.alerts(_nodes(1_000))
    assert ev.address == LAGGING and ev.data.is_sync


@pytest.mark.asyncio
async def test_short_lag_is_not_reported():
    ticker = Ticker()
    await ticker.alerts(_nodes(999))
    assert await ticker.alerts(_nodes(999)) == []  # 1 BTC block is less than the 1 hour default


@pytest.mark.asyncio
async def test_thorchain_is_not_checked_by_churn_in_height():
    # active_block_height is where a node churned in, not its current THORChain height
    ticker = Ticker()
    await ticker.alerts(_nodes(1_000))
    assert await ticker.alerts(_nodes(1_000)) == []
    assert Chains.THOR not in ticker.tracker.recent_max_blocks


@pytest.mark.asyncio
async def test_standby_nodes_are_not_checked():
    # standby and disabled nodes do not observe chains: their heights are months old (seen on mainnet)
    ticker = Ticker()
    stale = [_node(f'thor1standby{i}', 10, status=NodeInfo.STANDBY) for i in range(4)]
    await ticker.alerts(_nodes(1_000) + stale)
    assert await ticker.alerts(_nodes(1_000) + stale) == []

    # nor do they pull the expected height: 4 of them agree on a height above the active nodes
    ahead = [_node(f'thor1standby{i}', 5_000, status=NodeInfo.STANDBY) for i in range(4)]
    await ticker.alerts(_nodes(1_000) + ahead)
    assert ticker.tracker.recent_max_blocks[Chains.BTC] == 1_000


class CountingTracker:
    def __init__(self):
        self.calls = 0

    def estimate_block_height(self, _nodes):
        pass

    async def get_events(self):
        self.calls += 1
        return []


@pytest.mark.asyncio
async def test_every_tracker_runs_once_per_tick():
    notifier = NodeChangePersonalNotifier.__new__(NodeChangePersonalNotifier)
    notifier.logger = logging.getLogger('test')
    notifier.deps = SimpleNamespace(db=FakeDB())
    notifier._tick = 0
    names = ('online_tracker', 'chain_height_tracker', 'version_tracker', 'ip_address_tracker', 'churn_tracker',
             'slash_tracker', 'bond_tracker', 'presence_tracker')
    for name in names:
        setattr(notifier, name, CountingTracker())

    async def no_messages(_events):
        pass

    notifier._cast_messages_for_events = no_messages

    await notifier._handle_node_churn_bg_job(NodeSetChanges())

    assert {name: getattr(notifier, name).calls for name in names} == {name: 1 for name in names}
