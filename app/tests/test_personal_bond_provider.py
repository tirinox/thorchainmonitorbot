import pytest

from models.node_info import BondProvider, NodeEventType, NodeInfo, NodeSetChanges
from notify.personal.bond_provider import PersonalBondProviderNotifier


def make_notifier(threshold=1.0):
    notifier = object.__new__(PersonalBondProviderNotifier)
    notifier.min_bond_delta_to_react = 0.1
    notifier.min_provider_bond_to_notify = threshold

    async def memorize_bond_provider_ts(provider, node, ts, rune_bond):
        return 0, 0

    async def memorize_node_status_change_ts(node, ts, status):
        return None, 0

    notifier._memorize_bond_provider_ts = memorize_bond_provider_ts
    notifier._memorize_node_status_change_ts = memorize_node_status_change_ts
    return notifier


def make_node(address: str, providers, *, status=NodeInfo.ACTIVE):
    return NodeInfo(
        status=status,
        node_address=address,
        bond=sum(bp.rune_bond for bp in providers),
        bond_providers=list(providers),
    )


@pytest.mark.asyncio
async def test_bond_change_is_suppressed_when_prev_and_curr_are_below_threshold():
    notifier = make_notifier()
    prev_node = make_node('node-1', [BondProvider('bp-1', 0.4)])
    curr_node = make_node('node-1', [BondProvider('bp-1', 0.8)])
    changes = NodeSetChanges(nodes_all=[curr_node], nodes_previous=[prev_node])

    addresses, events = await notifier._handle_bond_amount_events(changes)

    assert addresses == set()
    assert events == []


@pytest.mark.asyncio
async def test_bond_change_is_sent_when_threshold_is_crossed():
    notifier = make_notifier()
    prev_node = make_node('node-1', [BondProvider('bp-1', 0.4)])
    curr_node = make_node('node-1', [BondProvider('bp-1', 1.2)])
    changes = NodeSetChanges(nodes_all=[curr_node], nodes_previous=[prev_node])

    addresses, events = await notifier._handle_bond_amount_events(changes)

    assert addresses == {'bp-1'}
    assert len(events) == 1
    assert events[0].type == NodeEventType.BOND_CHANGE
    assert events[0].data.prev_bond == pytest.approx(0.4)
    assert events[0].data.curr_bond == pytest.approx(1.2)


@pytest.mark.asyncio
async def test_churn_notifications_skip_low_bond_providers():
    notifier = make_notifier()
    node = make_node('node-1', [BondProvider('bp-low', 0.5), BondProvider('bp-high', 2.0)])
    changes = NodeSetChanges(nodes_activated=[node])

    addresses, events = await notifier._handle_churn_events(changes)

    assert addresses == {'bp-high'}
    assert [event.type for event in events] == [NodeEventType.CHURNING]
    assert [event.data.bond_provider for event in events] == ['bp-high']


@pytest.mark.asyncio
async def test_bond_provider_presence_alerts_are_kept_below_threshold():
    notifier = make_notifier()
    prev_node = make_node('node-1', [BondProvider('bp-1', 0.4)])
    curr_node = make_node('node-1', [])
    changes = NodeSetChanges(nodes_all=[curr_node], nodes_previous=[prev_node])

    addresses, events = await notifier._handle_bond_amount_events(changes)

    assert addresses == {'bp-1'}
    assert len(events) == 1
    assert events[0].type == NodeEventType.BP_PRESENCE
    assert not events[0].data.appeared
