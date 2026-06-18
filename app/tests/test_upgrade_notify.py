from types import SimpleNamespace
from typing import cast

import pytest

from api.aionode.types import ThorUpgradeProposal
from lib.depcont import DepContainer
from notify.public.upgrade_notify import UpgradeProposalsNotifier
from tests.fakes import FakeDB


class FakeUpgradeProposalsCfg:
    def __init__(self):
        self._values = {
            'new_proposal.enabled': True,
            'progress_update.enabled': True,
            'progress_update.minimum_progress_step_percent': 5.0,
            'progress_update.cooldown': '0',
        }

    def get(self, path, default=None):
        return self._values.get(path, default)

    def as_float(self, path, default=0.0):
        return float(self._values.get(path, default))


class FakeCfg:
    def __init__(self):
        self._section = FakeUpgradeProposalsCfg()

    def get(self, path, default=None):
        if path == 'upgrade_proposals':
            return self._section
        return default


def make_proposal(*, name='3.19.0', approved_percent=54.35, approved=False, approvers=None,
                  height=26_518_000, validators_to_quorum=12, info=''):
    return ThorUpgradeProposal(
        approved=approved,
        approved_percent=approved_percent,
        approvers=approvers or [
            'thor1rp6ll4p2qrj5k9mfelzmwv7ht0gv26pqxka8py',
            'thor1rvjz9xtyjuwf4antkjwsa94v4kctm4smu7alas',
        ],
        height=height,
        info=info,
        name=name,
        validators_to_quorum=validators_to_quorum,
    )


def make_notifier() -> UpgradeProposalsNotifier:
    deps = cast(DepContainer, cast(object, SimpleNamespace(db=FakeDB(), cfg=FakeCfg())))
    return UpgradeProposalsNotifier(deps)


@pytest.mark.asyncio
async def test_upgrade_proposals_notifier_ignores_initial_snapshot():
    notifier = make_notifier()
    sent = []

    async def capture(alert):
        sent.append(alert)

    notifier.pass_data_to_listeners = capture

    await notifier.on_data(None, [make_proposal()])

    assert sent == []


@pytest.mark.asyncio
async def test_upgrade_proposals_notifier_detects_new_proposal_after_empty_state():
    notifier = make_notifier()
    sent = []

    async def capture(alert):
        sent.append(alert)

    notifier.pass_data_to_listeners = capture

    await notifier.on_data(None, [])
    await notifier.on_data(None, [make_proposal(name='3.20.0', height=26_600_000)])

    assert len(sent) == 1
    assert sent[0].proposal.name == '3.20.0'
    assert sent[0].proposal.height == 26_600_000


@pytest.mark.asyncio
async def test_upgrade_proposals_notifier_detects_progress_update_above_threshold():
    notifier = make_notifier()
    sent = []

    async def capture(alert):
        sent.append(alert)

    notifier.pass_data_to_listeners = capture

    await notifier.on_data(None, [make_proposal(approved_percent=54.35)])
    await notifier.on_data(None, [make_proposal(approved_percent=60.00, validators_to_quorum=9)])

    assert len(sent) == 1
    assert sent[0].previous.approved_percent == 54.35
    assert sent[0].current.approved_percent == 60.0
    assert sent[0].current.validators_to_quorum == 9


@pytest.mark.asyncio
async def test_upgrade_proposals_notifier_ignores_small_progress_change():
    notifier = make_notifier()
    sent = []

    async def capture(alert):
        sent.append(alert)

    notifier.pass_data_to_listeners = capture

    await notifier.on_data(None, [make_proposal(approved_percent=54.35)])
    await notifier.on_data(None, [make_proposal(approved_percent=57.00)])

    assert sent == []


@pytest.mark.asyncio
async def test_upgrade_proposals_notifier_detects_status_change_even_without_large_percent_step():
    notifier = make_notifier()
    sent = []

    async def capture(alert):
        sent.append(alert)

    notifier.pass_data_to_listeners = capture

    await notifier.on_data(None, [make_proposal(approved_percent=66.60, approved=False)])
    await notifier.on_data(None, [make_proposal(approved_percent=66.61, approved=True, validators_to_quorum=0)])

    assert len(sent) == 1
    assert sent[0].previous.approved is False
    assert sent[0].current.approved is True

