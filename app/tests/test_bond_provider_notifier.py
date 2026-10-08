import math
from types import SimpleNamespace

import pytest

from api.midgard.name_service import NameMap
from lib.date_utils import DAY
from lib.money import calculate_apy
from models.node_info import NodeSetChanges, NodeInfo, BondProvider, EventProviderBondChange, NodeEventType
from notify.personal import bond_provider as bp_module
from notify.personal.base import BasePersonalNotifier
from notify.personal.bond_provider import PersonalBondProviderNotifier
from tests.fakes import FakeDB

NODE = 'thor1node'
PROVIDER = 'thor1provider'
TICK = 5.0  # the node fetch period


PREV_CHURN_BLOCK = 100_000
CHURN_PERIOD_BLOCKS = 43_200  # 3 days


def _node(bond=None, address=NODE, provider=PROVIDER):
    providers = [BondProvider(provider, bond)] if bond is not None else []
    return NodeInfo(status=NodeInfo.ACTIVE, node_address=address, bond=bond or 0.0, bond_providers=providers,
                    active_block_height=PREV_CHURN_BLOCK)


def _changes(prev_bond, curr_bond, churn=False):
    curr = _node(curr_bond)
    return NodeSetChanges(nodes_previous=[_node(prev_bond)], nodes_all=[curr],
                          nodes_activated=[curr] if churn else [],
                          block_no=PREV_CHURN_BLOCK + CHURN_PERIOD_BLOCKS)


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def notifier(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(bp_module, 'now_ts', clock)
    deps = SimpleNamespace(cfg=SimpleNamespace(as_float=lambda _key, default: default), db=FakeDB())
    n = PersonalBondProviderNotifier(deps)
    n.clock = clock
    return n


async def _bond_events(notifier, prev_bond, curr_bond, churn=False):
    _, events = await notifier._handle_bond_amount_events(_changes(prev_bond, curr_bond, churn))
    return [e for e in events if e.type == NodeEventType.BOND_CHANGE]


@pytest.mark.asyncio
async def test_time_since_last_change_spans_the_whole_churn(notifier):
    await notifier._handle_bond_amount_events(_changes(None, 100.0))  # the provider bonds

    for _ in range(3):  # quiet ticks must not touch the stored time
        notifier.clock.t += TICK
        assert await _bond_events(notifier, 100.0, 100.0) == []

    notifier.clock.t += 3 * DAY - 3 * TICK
    [ev] = await _bond_events(notifier, 100.0, 101.0, churn=True)
    assert ev.data.duration_sec == pytest.approx(3 * DAY)
    assert ev.data.churn_period_sec == pytest.approx(3 * DAY)
    assert ev.data.apy == pytest.approx(calculate_apy(100.0, 101.0, 3 * DAY))

    notifier.clock.t += TICK
    assert await _bond_events(notifier, 101.0, 101.0) == []

    notifier.clock.t += 3 * DAY - TICK
    [ev] = await _bond_events(notifier, 101.0, 102.0, churn=True)
    assert ev.data.duration_sec == pytest.approx(3 * DAY)


@pytest.mark.asyncio
async def test_apy_is_counted_over_the_churn_period(notifier):
    # the same reward on two nodes; one bond also changed in the middle of the period (a slash, a small deposit)
    other = 'thor1other'

    def changes(prev, curr, churn=False):
        nodes = [(NODE, PROVIDER), (other, 'thor1provider2')]
        currs = [_node(curr[i], a, p) for i, (a, p) in enumerate(nodes)]
        return NodeSetChanges(nodes_previous=[_node(prev[i], a, p) for i, (a, p) in enumerate(nodes)],
                              nodes_all=currs, nodes_activated=currs if churn else [],
                              block_no=PREV_CHURN_BLOCK + CHURN_PERIOD_BLOCKS)

    await notifier._handle_bond_amount_events(changes((None, None), (100.0, 100.0)))
    notifier.clock.t += 2 * DAY
    await notifier._handle_bond_amount_events(changes((100.0, 100.0), (100.0, 99.9)))
    notifier.clock.t += DAY
    _, events = await notifier._handle_bond_amount_events(changes((100.0, 99.9), (101.0, 100.9), churn=True))
    a, b = [e.data for e in events if e.type == NodeEventType.BOND_CHANGE]

    assert a.duration_sec == pytest.approx(3 * DAY) and b.duration_sec == pytest.approx(DAY)
    assert a.apy == pytest.approx(calculate_apy(100.0, 101.0, 3 * DAY))
    assert b.apy == pytest.approx(calculate_apy(99.9, 100.9, 3 * DAY))


@pytest.mark.asyncio
async def test_left_provider_is_forgotten(notifier):
    await notifier._handle_bond_amount_events(_changes(None, 100.0))
    key = notifier.bond_provider_status_hash_key(PROVIDER, NODE)
    assert key in notifier.deps.db.redis.hashes[notifier.DB_KEY_BOND_PROVIDER_STATUS]

    await notifier._handle_bond_amount_events(_changes(100.0, None))
    assert key not in notifier.deps.db.redis.hashes[notifier.DB_KEY_BOND_PROVIDER_STATUS]


def test_apy_needs_a_real_reward_period():
    # a 5 s "period" used to raise OverflowError: 1.003 ** (365 days / 5 s)
    assert EventProviderBondChange(PROVIDER, 100.0, 100.3, on_churn=True, churn_period_sec=TICK).apy is None
    assert EventProviderBondChange(PROVIDER, 100.0, 100.3, on_churn=False, churn_period_sec=3 * DAY).apy is None
    assert EventProviderBondChange(PROVIDER, 100.0, 100.3, on_churn=True, churn_period_sec=0).apy is None  # unknown
    assert EventProviderBondChange(PROVIDER, 100.0, 100.3, on_churn=True, churn_period_sec=3 * DAY).apy > 0


def test_apy_overflow_is_infinite():
    assert calculate_apy(1.0, 1e6, DAY) == math.inf
    assert EventProviderBondChange(PROVIDER, 1.0, 1e6, on_churn=True, churn_period_sec=DAY).apy is None


class FakeWatcher:
    async def all_users_for_many_nodes(self, addresses):
        return {a: ['bad', 'good'] for a in addresses}

    @staticmethod
    def all_affected_users(address_to_user):
        return {u for users in address_to_user.values() for u in users}

    @staticmethod
    def reverse(address_to_user):
        return {'bad': list(address_to_user), 'good': list(address_to_user)}


class OneBadUserNotifier(BasePersonalNotifier):
    def __init__(self):
        async def load_names(_addresses):
            return NameMap.empty()

        async def get_name_map():
            return NameMap.empty()

        async def get_settings_multi(users):
            return {u: {} for u in users}

        async def get_from_db(_user, _db):
            return None

        deps = SimpleNamespace(
            db=None,
            name_service=SimpleNamespace(safely_load_thornames_from_address_set=load_names,
                                         get_local_service=lambda _u: SimpleNamespace(get_name_map=get_name_map)),
            settings_manager=SimpleNamespace(get_settings_multi=get_settings_multi),
            loc_man=SimpleNamespace(get_from_db=get_from_db),
        )
        super().__init__(deps, FakeWatcher())
        self.sent = []

    async def on_data(self, sender, data):
        pass

    def get_users_from_event(self, ev, address_to_user):
        return address_to_user.get(ev)

    async def generate_message_text(self, loc, group, settings, user, user_watch_addy_list, name_map):
        if user == 'bad':
            raise OverflowError('(34, Result too large)')
        return 'hello'

    async def _send_message(self, message, settings, user, msg_type):
        self.sent.append(user)


@pytest.mark.asyncio
async def test_one_failing_user_does_not_stop_the_others():
    notifier = OneBadUserNotifier()
    await notifier.group_and_send_messages({'thor1a'}, ['thor1a'])
    assert notifier.sent == ['good']
