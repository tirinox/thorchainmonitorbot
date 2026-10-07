import asyncio
from types import SimpleNamespace
from typing import cast

import pytest

from lib.depcont import DepContainer
from models.mimir import MimirVoteOption, MimirVoting
from notify.public.voting_notify import VotingNotifier
from tests.fakes import FakeDB


@pytest.mark.asyncio
async def test_voting_notifier_applies_global_cooldown_across_different_keys():
    notifier = VotingNotifier.__new__(VotingNotifier)
    notifier.deps = cast(
        DepContainer,
        cast(object, SimpleNamespace(db=FakeDB(), mimir_const_holder=None)),
    )
    notifier.notification_cd_time = 1.0
    notifier.global_notification_cd_time = 0.05
    notifier.global_notification_cd_hits = 2

    sent = []

    class FakeRecorder:
        async def get_alert_for_key(self, key, period, holder=None, triggered_option=None):
            return {
                'key': key,
                'period': period,
                'option': triggered_option.value if triggered_option else None,
            }

    async def capture(alert):
        sent.append(alert)

    notifier.vote_recorder = FakeRecorder()
    notifier.pass_data_to_listeners = capture

    async def trigger(key: str, option_value: int):
        option = MimirVoteOption(value=option_value, signer_count=7)
        voting = MimirVoting(key, {option_value: option}, active_nodes_count=100)
        await notifier._on_progress_changed(key, 0.0, voting, option)

    await trigger('KEY_ONE', 1)
    await trigger('KEY_TWO', 2)
    await trigger('KEY_THREE', 3)

    assert [item['key'] for item in sent] == ['KEY_ONE', 'KEY_TWO']

    await asyncio.sleep(notifier.global_notification_cd_time + 0.01)
    await trigger('KEY_FOUR', 4)

    assert [item['key'] for item in sent] == ['KEY_ONE', 'KEY_TWO', 'KEY_FOUR']


@pytest.mark.asyncio
async def test_voting_notifier_skips_options_below_min_votes_pct():
    notifier = VotingNotifier.__new__(VotingNotifier)
    notifier.progress_tolerance = 1.0
    notifier.min_votes_pct = 10.0
    notifier.IGNORE_IF_THERE_ARE_MORE_UPDATES_THAN = 6
    notifier.logger = SimpleNamespace(info=lambda *_: None, warning=lambda *_: None)

    # 100 nodes: KEY_LOW 9 votes (9%), KEY_EDGE 10 votes (10%), KEY_HIGH 30 votes (30%)
    voting_list = [
        MimirVoting(key, {1: MimirVoteOption(1, signer_count=n)}, active_nodes_count=100)
        for key, n in (('KEY_LOW', 9), ('KEY_EDGE', 10), ('KEY_HIGH', 30))
    ]
    for v in voting_list:
        v.top_options  # fills option.progress

    async def prev_state():
        return {v.key: {'1': 0.0} for v in voting_list}

    async def save(_):
        pass

    fired = []

    async def on_progress(key, *_):
        fired.append(key)

    notifier.read_prev_state = prev_state
    notifier._save_prev_state = save
    notifier._on_progress_changed = on_progress

    data = SimpleNamespace(voting_manager=SimpleNamespace(all_voting_list=voting_list))
    await notifier.on_data(None, data)

    assert fired == ['KEY_EDGE', 'KEY_HIGH']
