import json
from types import SimpleNamespace
from typing import cast

import pytest

from api.aionode.types import ThorUpgradeProposal
from lib.depcont import DepContainer
from models.upgrade_proposal import AlertUpgradeProposalNew, AlertUpgradeProposalProgress, \
    AlertUpgradeProposalApproved, AlertUpgradeProposalExpired
from notify.public.upgrade_notify import UpgradeProposalsNotifier
from tests.fakes import FakeDB

HEIGHT = 26_518_000
APPROVERS = [
    'thor1rp6ll4p2qrj5k9mfelzmwv7ht0gv26pqxka8py',
    'thor1rvjz9xtyjuwf4antkjwsa94v4kctm4smu7alas',
]


class FakeCfg:
    def __init__(self, **overrides):
        self._values = {
            'upgrade_proposals.new_proposal.enabled': True,
            'upgrade_proposals.progress_update.enabled': True,
            'upgrade_proposals.progress_update.minimum_progress_step_percent': 5.0,
            'upgrade_proposals.progress_update.cooldown': '0',
            'upgrade_proposals.near_quorum.validators_to_quorum': 5,
        }
        self._values.update(overrides)

    def get(self, path, default=None):
        return self._values.get(path, default)

    def as_float(self, path, default=0.0):
        return float(self._values.get(path, default))


class FakeLastBlock:
    def __init__(self, block):
        self.block = block

    async def get_thor_block(self):
        return self.block


class FakeNodeCache:
    def __init__(self, addresses):
        self.addresses = addresses

    async def get(self):
        nodes = [SimpleNamespace(node_address=a) for a in self.addresses]
        return SimpleNamespace(active_nodes=nodes)


class FakeConnector:
    def __init__(self):
        self.version = {'current': '3.19.0', 'next': '3.19.0'}

    async def query_version(self):
        return self.version


def make_proposal(*, name='3.20.0', approved_percent=54.35, approved=False, approvers=None,
                  height=HEIGHT, validators_to_quorum=12, info='', rejecters=None):
    return ThorUpgradeProposal(
        approved=approved,
        approved_percent=approved_percent,
        approvers=approvers if approvers is not None else list(APPROVERS),
        height=height,
        info=info,
        name=name,
        validators_to_quorum=validators_to_quorum,
        rejecters=rejecters or [],
    )


class Harness:
    def __init__(self, block=HEIGHT - 1000, active=(), **cfg):
        self.last_block = FakeLastBlock(block)
        self.connector = FakeConnector()
        self.db = FakeDB()
        deps = SimpleNamespace(db=self.db, cfg=FakeCfg(**cfg), last_block_cache=self.last_block,
                               node_cache=FakeNodeCache(list(active)), thor_connector=self.connector)
        self.notifier = UpgradeProposalsNotifier(cast(DepContainer, cast(object, deps)))
        self.sent = []

        async def capture(alert):
            self.sent.append(alert)

        self.notifier.pass_data_to_listeners = capture

    async def feed(self, *proposals):
        await self.notifier.on_data(None, list(proposals))
        return self

    def of_type(self, t):
        return [a for a in self.sent if isinstance(a, t)]


@pytest.mark.asyncio
async def test_ignores_initial_snapshot():
    h = await Harness().feed(make_proposal())
    assert h.sent == []


@pytest.mark.asyncio
async def test_initial_snapshot_with_approved_proposal_does_not_announce_approval_later():
    h = Harness()
    await h.feed(make_proposal(approved=True, approved_percent=70, validators_to_quorum=0))
    await h.feed(make_proposal(approved=True, approved_percent=71, validators_to_quorum=0))
    assert h.sent == []


@pytest.mark.asyncio
async def test_detects_new_proposal_after_empty_state():
    h = Harness()
    await h.feed()
    await h.feed(make_proposal(name='3.20.0', height=26_600_000))

    assert len(h.sent) == 1
    assert isinstance(h.sent[0], AlertUpgradeProposalNew)
    assert h.sent[0].proposal.name == '3.20.0'
    assert h.sent[0].blocks_left == 26_600_000 - (HEIGHT - 1000)


@pytest.mark.asyncio
async def test_progress_update_above_threshold():
    h = Harness()
    await h.feed(make_proposal(approved_percent=54.35))
    await h.feed(make_proposal(approved_percent=60.00, validators_to_quorum=9))

    assert len(h.sent) == 1
    alert = h.sent[0]
    assert isinstance(alert, AlertUpgradeProposalProgress)
    assert alert.previous.approved_percent == 54.35
    assert alert.current.approved_percent == 60.0
    assert alert.near_quorum is False


@pytest.mark.asyncio
async def test_ignores_small_progress_change():
    h = Harness()
    await h.feed(make_proposal(approved_percent=54.35))
    await h.feed(make_proposal(approved_percent=57.00))
    assert h.sent == []


@pytest.mark.asyncio
async def test_approval_is_announced_once_despite_cooldown_and_flapping():
    h = Harness(**{'upgrade_proposals.progress_update.cooldown': '30m'})
    await h.feed(make_proposal(approved_percent=50.0))
    await h.feed(make_proposal(approved_percent=60.0, validators_to_quorum=8))  # progress, cooldown starts
    await h.feed(make_proposal(approved_percent=66.7, approved=True, validators_to_quorum=0))
    await h.feed(make_proposal(approved_percent=66.0, approved=False, validators_to_quorum=1))
    await h.feed(make_proposal(approved_percent=67.0, approved=True, validators_to_quorum=0))

    approved = h.of_type(AlertUpgradeProposalApproved)
    assert len(approved) == 1
    assert approved[0].is_late is False
    assert approved[0].seconds_left == 1000 * 6.0


@pytest.mark.asyncio
async def test_no_progress_alert_together_with_approval():
    h = Harness()
    await h.feed(make_proposal(approved_percent=50.0))
    await h.feed(make_proposal(approved_percent=70.0, approved=True, validators_to_quorum=0))

    assert [type(a) for a in h.sent] == [AlertUpgradeProposalApproved]


@pytest.mark.asyncio
async def test_near_quorum_lists_votes_and_bypasses_cooldown():
    active = APPROVERS + ['thor1aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1111',
                          'thor1bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb2222']
    h = Harness(active=active, **{'upgrade_proposals.progress_update.cooldown': '30m'})
    await h.feed(make_proposal(approved_percent=50.0))
    await h.feed(make_proposal(approved_percent=56.0, validators_to_quorum=10))  # progress, cooldown starts
    await h.feed(make_proposal(approved_percent=57.0, validators_to_quorum=2,
                               rejecters=[active[3]]))  # near quorum: sent despite cooldown and small step
    await h.feed(make_proposal(approved_percent=58.0, validators_to_quorum=1))  # nothing, cooldown

    progress = h.of_type(AlertUpgradeProposalProgress)
    assert len(progress) == 2
    assert progress[0].near_quorum is False
    assert progress[1].near_quorum is True
    votes = progress[1].votes
    assert votes.approvers == APPROVERS
    assert votes.not_voted == [active[2]]
    assert votes.rejecters == [active[3]]
    assert votes.active_count == 4
    assert votes.quorum_count == 3
    assert progress[1].current_version == '3.19.0'


@pytest.mark.asyncio
async def test_lost_quorum_is_a_progress_update():
    h = Harness()
    await h.feed(make_proposal(approved_percent=66.7, approved=True, validators_to_quorum=0))
    await h.feed(make_proposal(approved_percent=66.0, approved=False, validators_to_quorum=1))

    progress = h.of_type(AlertUpgradeProposalProgress)
    assert len(progress) == 1
    assert progress[0].previous.approved and not progress[0].current.approved


@pytest.mark.asyncio
async def test_empty_answer_before_height_is_ignored():
    h = Harness(block=HEIGHT - 100)
    await h.feed(make_proposal())
    await h.feed()  # API glitch
    await h.feed(make_proposal())

    assert h.sent == []


@pytest.mark.asyncio
async def test_proposal_gone_after_height_approved_late():
    h = Harness(block=HEIGHT - 100)
    await h.feed(make_proposal(approved_percent=60.0, validators_to_quorum=6))
    h.last_block.block = HEIGHT + 5
    h.connector.version = {'current': '3.19.0', 'next': '3.20.0'}
    await h.feed()
    await h.feed()

    approved = h.of_type(AlertUpgradeProposalApproved)
    assert len(approved) == 1
    assert approved[0].is_late is True
    assert h.of_type(AlertUpgradeProposalExpired) == []


@pytest.mark.asyncio
async def test_proposal_gone_after_height_already_approved_is_silent():
    h = Harness(block=HEIGHT - 100)
    await h.feed(make_proposal(approved_percent=50.0))
    await h.feed(make_proposal(approved_percent=70.0, approved=True, validators_to_quorum=0))
    h.last_block.block = HEIGHT + 5
    await h.feed()

    assert [type(a) for a in h.sent] == [AlertUpgradeProposalApproved]


@pytest.mark.asyncio
async def test_proposal_gone_after_height_without_quorum_expires():
    h = Harness(block=HEIGHT - 100)
    await h.feed(make_proposal(approved_percent=40.0))
    h.last_block.block = HEIGHT + 5
    await h.feed()
    await h.feed()

    assert [type(a) for a in h.sent] == [AlertUpgradeProposalExpired]


@pytest.mark.asyncio
async def test_reads_old_state_keyed_by_height_and_name():
    h = Harness()
    old = make_proposal(approved_percent=50.0)
    await h.db.redis.set(UpgradeProposalsNotifier.DB_KEY_LAST_STATE,
                         json.dumps({f'{old.height}:{old.name}': old._asdict()}))
    await h.feed(make_proposal(approved_percent=51.0))

    assert h.sent == []


def _all_localizations():
    from comm.localization.eng_base import BaseLocalization
    from comm.localization.rus import RussianLocalization
    from comm.localization.twitter_eng import TwitterEnglishLocalization
    from lib.config import Config
    cfg = Config(data={'twitter': {'max_length': 280}})
    return [BaseLocalization(cfg), RussianLocalization(cfg), TwitterEnglishLocalization(cfg)]


@pytest.mark.parametrize('loc', _all_localizations(), ids=lambda loc: loc.name)
def test_texts_render_in_all_localizations(loc):
    from models.upgrade_proposal import UpgradeProposalVotes

    block = HEIGHT - 14_400  # one day
    prev = make_proposal(approved_percent=60.0, validators_to_quorum=8)
    cur = make_proposal(approved_percent=63.5, validators_to_quorum=3, approvers=APPROVERS + ['x'])
    votes = UpgradeProposalVotes(approvers=list(APPROVERS), not_voted=['thor1aaaa1111', 'thor1bbbb2222'],
                                 rejecters=['thor1cccc3333'])
    approved = make_proposal(approved=True, approved_percent=67.0, validators_to_quorum=0)

    texts = [
        loc.notification_text_upgrade_proposal_new(AlertUpgradeProposalNew(prev, block)),
        loc.notification_text_upgrade_proposal_progress(AlertUpgradeProposalProgress(prev, cur, block)),
        loc.notification_text_upgrade_proposal_progress(
            AlertUpgradeProposalProgress(prev, cur, block, votes=votes, near_quorum=True)),
        loc.notification_text_upgrade_proposal_approved(AlertUpgradeProposalApproved(approved, block)),
        loc.notification_text_upgrade_proposal_approved(
            AlertUpgradeProposalApproved(approved, HEIGHT + 3, is_late=True)),
        loc.notification_text_upgrade_proposal_expired(AlertUpgradeProposalExpired(prev, HEIGHT + 3)),
    ]
    for text in texts:
        assert '3.20.0' in text

    with_laggards = texts[2]
    assert '1111' in with_laggards and '2222' in with_laggards and '3333' in with_laggards
    assert 'thor1aaaa' not in with_laggards
    assert str(HEIGHT) in texts[3]


@pytest.mark.asyncio
async def test_history_stores_only_changes():
    h = Harness()
    await h.feed(make_proposal(approved_percent=50.0))
    await h.feed(make_proposal(approved_percent=50.0))
    await h.feed(make_proposal(approved_percent=52.0))
    await h.feed(make_proposal(approved_percent=52.0))

    history = await h.notifier.read_history('3.20.0')
    assert [pct for _, pct in history] == [50.0, 52.0]


@pytest.mark.asyncio
async def test_new_alert_carries_votes_history_and_version():
    h = Harness(active=APPROVERS + ['thor1zzzz'])
    await h.feed()
    await h.feed(make_proposal(approved_percent=33.0))

    alert = h.sent[0]
    assert isinstance(alert, AlertUpgradeProposalNew)
    assert alert.votes.not_voted == ['thor1zzzz']
    assert [pct for _, pct in alert.history] == [33.0]
    assert alert.current_version == '3.19.0'


def test_card_params():
    from models.upgrade_proposal import UpgradeProposalVotes, upgrade_card_params

    now = 1_790_000_000
    votes = UpgradeProposalVotes(approvers=['thor1aaaa'] * 67, not_voted=['thor1bbbb'] * 35, rejecters=['thor1cccc'] * 2)
    prev = make_proposal(approved_percent=60.0)
    cur = make_proposal(approved_percent=64.42, validators_to_quorum=3)
    alert = AlertUpgradeProposalProgress(prev, cur, HEIGHT - 30_400, votes=votes, near_quorum=True,
                                         history=[(now - 7200, 50.0), (now - 3600, 60.0)], current_version='3.19.0')
    p = upgrade_card_params(alert, now=now)

    assert p['kind'] == 'near'
    assert p['active_count'] == 104 and p['quorum_count'] == 70
    assert p['eta_parts'] == [[2, 'd'], [2, 'h'], [40, 'm']]
    assert p['history'][-1] == {'ts': now, 'pct': 64.42}
    assert p['prev_percent'] == 60.0
    assert [n['vote'] for n in p['nodes']].count('none') == 35
    assert p['nodes'][0]['short'] == 'aaaa'

    approved = AlertUpgradeProposalApproved(make_proposal(approved=True), HEIGHT - 100, votes=votes)
    assert upgrade_card_params(approved, now=now)['kind'] == 'approved'
    assert upgrade_card_params(approved, now=now)['eta_parts'] == [[0, 'h'], [10, 'm']]


@pytest.mark.asyncio
async def test_presenter_sends_the_card_with_the_text_as_caption():
    from comm.localization.eng_base import BaseLocalization
    from lib.config import Config
    from models.upgrade_proposal import UpgradeProposalVotes
    from notify.alert_presenter import AlertPresenter
    from notify.channel import MessageType

    class FakeRenderer:
        def __init__(self):
            self.calls = []

        async def render(self, template, params):
            self.calls.append((template, params))
            return b'png'

    class FakeBroadcaster:
        def __init__(self):
            self.messages = []

        async def broadcast_to_all(self, msg_type, message_gen, *args, **kwargs):
            self.messages.append((msg_type, await message_gen(BaseLocalization(Config(data={})))))

    broadcaster = FakeBroadcaster()
    presenter = cast(AlertPresenter, object.__new__(AlertPresenter))
    presenter.deps = SimpleNamespace(broadcaster=broadcaster)
    presenter.renderer = FakeRenderer()
    presenter.use_renderer = True

    votes = UpgradeProposalVotes(approvers=list(APPROVERS), not_voted=['thor1zzzz'])
    alert = AlertUpgradeProposalApproved(make_proposal(approved=True), HEIGHT - 600, votes=votes)
    await presenter.handle_data(alert)

    template, params = presenter.renderer.calls[0]
    assert template == 'upgrade_proposal.jinja2'
    assert params['kind'] == 'approved'
    msg_type, message = broadcaster.messages[0]
    assert msg_type == 'public:upgrade_proposals:approved'
    assert message.message_type == MessageType.PHOTO
    assert 'APPROVED' in message.text
