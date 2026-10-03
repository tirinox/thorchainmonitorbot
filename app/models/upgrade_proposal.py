from datetime import datetime, timezone
from typing import NamedTuple, List, Optional, Tuple

from api.aionode.types import ThorUpgradeProposal
from lib.constants import THOR_BLOCK_TIME

# (timestamp, approved_percent)
UpgradeHistory = List[Tuple[float, float]]


def short_node_address(address: str, n=4) -> str:
    return address[-n:] if address else '?'


class UpgradeProposalVotes(NamedTuple):
    """How the active validators voted; only the active ones count for the quorum."""
    approvers: List[str] = []
    not_voted: List[str] = []
    rejecters: List[str] = []

    @property
    def active_count(self):
        return len(self.approvers) + len(self.not_voted) + len(self.rejecters)

    @property
    def quorum_count(self):
        # THORNode: approved if approving * 3 >= active * 2
        return (self.active_count * 2 + 2) // 3


def _blocks_left(alert) -> Optional[int]:
    if not alert.current_block or not alert.proposal.height:
        return None
    return alert.proposal.height - alert.current_block


def _seconds_left(alert) -> Optional[float]:
    blocks = _blocks_left(alert)
    return None if blocks is None else max(0, blocks) * THOR_BLOCK_TIME


class AlertUpgradeProposalNew(NamedTuple):
    proposal: ThorUpgradeProposal
    current_block: int = 0
    votes: Optional[UpgradeProposalVotes] = None
    history: UpgradeHistory = []
    current_version: str = ''

    blocks_left = property(_blocks_left)
    seconds_left = property(_seconds_left)


class AlertUpgradeProposalProgress(NamedTuple):
    previous: ThorUpgradeProposal
    current: ThorUpgradeProposal
    current_block: int = 0
    votes: Optional[UpgradeProposalVotes] = None
    history: UpgradeHistory = []
    current_version: str = ''
    # a few validators away from the quorum: the texts name those who have not approved yet
    near_quorum: bool = False

    @property
    def proposal(self):
        return self.current

    blocks_left = property(_blocks_left)
    seconds_left = property(_seconds_left)


class AlertUpgradeProposalApproved(NamedTuple):
    """Sent once per proposal name, when the validators reach the quorum."""
    proposal: ThorUpgradeProposal
    current_block: int = 0
    votes: Optional[UpgradeProposalVotes] = None
    history: UpgradeHistory = []
    current_version: str = ''
    # the proposal left the list (its height passed) before the bot saw it approved
    is_late: bool = False

    blocks_left = property(_blocks_left)
    seconds_left = property(_seconds_left)


class AlertUpgradeProposalExpired(NamedTuple):
    """The upgrade height passed without the quorum; THORNode dropped the proposal."""
    proposal: ThorUpgradeProposal
    current_block: int = 0


def _eta_parts(seconds: Optional[float]) -> List[List]:
    """[[1, 'd'], [12, 'h'], [30, 'm']]: days are left out when zero, minutes are kept."""
    if seconds is None:
        return []
    seconds = int(seconds)
    d, h, m = seconds // 86400, seconds % 86400 // 3600, seconds % 3600 // 60
    parts = [[d, 'd']] if d else []
    return parts + [[h, 'h'], [m, 'm']]


def upgrade_card_params(alert, now: Optional[float] = None) -> dict:
    """Parameters of renderer/templates/upgrade_proposal.jinja2"""
    p: ThorUpgradeProposal = alert.proposal
    votes = alert.votes or UpgradeProposalVotes(approvers=list(p.approvers or []))
    now = now or datetime.now(timezone.utc).timestamp()

    approved = isinstance(alert, AlertUpgradeProposalApproved) or p.approved
    near_quorum = bool(getattr(alert, 'near_quorum', False))
    prev = getattr(alert, 'previous', None)

    seconds_left = alert.seconds_left
    eta_ts = now + seconds_left if seconds_left else None

    history = [{'ts': ts, 'pct': pct} for ts, pct in (alert.history or [])]
    if history and history[-1]['ts'] < now:
        history.append({'ts': now, 'pct': p.approved_percent})  # the step line goes up to now

    active_count = votes.active_count
    return {
        'kind': 'approved' if approved else ('near' if near_quorum else 'voting'),
        'is_new': isinstance(alert, AlertUpgradeProposalNew),
        'version': p.name,
        'current_version': alert.current_version,
        'approved': approved,
        'near_quorum': near_quorum,
        'is_late': bool(getattr(alert, 'is_late', False)),
        'approved_percent': p.approved_percent,
        'prev_percent': prev.approved_percent if prev else None,
        'approvers': len(votes.approvers),
        'rejecters': len(votes.rejecters),
        'not_voted': len(votes.not_voted),
        'active_count': active_count,
        'quorum_count': votes.quorum_count,
        'validators_to_quorum': p.validators_to_quorum,
        'height': p.height,
        'current_block': alert.current_block,
        'blocks_left': alert.blocks_left,
        'eta_parts': _eta_parts(seconds_left),
        'eta_date': datetime.fromtimestamp(eta_ts, timezone.utc).strftime('%d.%m.%Y %H:%M UTC') if eta_ts else '',
        'nodes': (
            [{'short': short_node_address(a), 'vote': 'approve'} for a in votes.approvers] +
            [{'short': short_node_address(a), 'vote': 'none'} for a in votes.not_voted] +
            [{'short': short_node_address(a), 'vote': 'reject'} for a in votes.rejecters]
        ),
        'history': history,
    }
