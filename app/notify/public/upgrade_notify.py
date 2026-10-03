import json
from typing import Dict, List, Optional

from semver import VersionInfo

from api.aionode.types import ThorUpgradeProposal
from lib.cooldown import Cooldown
from lib.date_utils import parse_timespan_to_seconds
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.date_utils import now_ts, DAY
from lib.logs import WithLogger
from models.upgrade_proposal import AlertUpgradeProposalNew, AlertUpgradeProposalProgress, \
    AlertUpgradeProposalApproved, AlertUpgradeProposalExpired, UpgradeProposalVotes, UpgradeHistory


def parse_proposal_version(name: str) -> Optional[VersionInfo]:
    try:
        return VersionInfo.parse(name.strip().lstrip('vV'))
    except (ValueError, TypeError, AttributeError):
        return None


class UpgradeProposalsNotifier(INotified, WithDelegates, WithLogger):
    """
    Watches /thorchain/upgrade_proposals. THORNode keeps a proposal (and its votes) until the block height
    passes the proposal's height, then deletes it. So a proposal that left the list is either executed
    (it had the quorum) or expired; while the height is not reached, a missing proposal is a glitch of the API.
    """

    DB_KEY_LAST_STATE = 'UpgradeProposals:LastState'  # JSON: name -> proposal
    DB_KEY_ANNOUNCED = 'UpgradeProposals:Announced:'  # + kind: a set of proposal names
    DB_KEY_HISTORY = 'UpgradeProposals:History:'  # + name: JSON [[ts, approved_percent], ...]
    HISTORY_MAX_POINTS = 1000
    HISTORY_TTL = 60 * DAY

    ANNOUNCED_NEW = 'New'
    ANNOUNCED_APPROVED = 'Approved'
    ANNOUNCED_NEAR_QUORUM = 'NearQuorum'
    ANNOUNCED_FINISHED = 'Finished'

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        cfg = deps.cfg
        self.is_new_proposal_enabled = bool(cfg.get('upgrade_proposals.new_proposal.enabled', True))
        self.is_progress_update_enabled = bool(cfg.get('upgrade_proposals.progress_update.enabled', True))
        self.min_progress_step_pct = cfg.as_float('upgrade_proposals.progress_update.minimum_progress_step_percent', 5.0)
        self.progress_cd_sec = parse_timespan_to_seconds(
            str(cfg.get('upgrade_proposals.progress_update.cooldown', '30m'))
        )
        self.is_approved_enabled = bool(cfg.get('upgrade_proposals.approved.enabled', True))
        self.is_expired_enabled = bool(cfg.get('upgrade_proposals.expired.enabled', True))
        # "almost there": this many validators or fewer are missing to the quorum
        self.near_quorum_validators = int(cfg.get('upgrade_proposals.near_quorum.validators_to_quorum', 5))
        self._version_cache = None

    # ---- state ----

    async def _read_prev_state(self) -> Optional[Dict[str, ThorUpgradeProposal]]:
        raw_data = await self.deps.db.redis.get(self.DB_KEY_LAST_STATE)
        if raw_data is None:
            return None
        try:
            data = json.loads(raw_data)
            # keyed by name; the old state was keyed by "height:name", so the key is not trusted
            proposals = (ThorUpgradeProposal.from_json(item) for item in data.values())
            return {p.name: p for p in proposals}
        except (TypeError, ValueError, AttributeError):
            return None

    async def _save_state(self, proposals: Dict[str, ThorUpgradeProposal]):
        data = {name: proposal._asdict() for name, proposal in proposals.items()}
        await self.deps.db.redis.set(self.DB_KEY_LAST_STATE, json.dumps(data))

    async def _was_announced(self, kind: str, name: str) -> bool:
        return bool(await self.deps.db.redis.sismember(self.DB_KEY_ANNOUNCED + kind, name))

    async def _mark_announced(self, kind: str, name: str):
        await self.deps.db.redis.sadd(self.DB_KEY_ANNOUNCED + kind, name)

    async def _announce_once(self, kind: str, name: str, make_alert) -> bool:
        if await self._was_announced(kind, name):
            return False
        await self._mark_announced(kind, name)
        await self.pass_data_to_listeners(await make_alert())
        return True

    async def read_history(self, name: str) -> UpgradeHistory:
        raw = await self.deps.db.redis.get(self.DB_KEY_HISTORY + name)
        try:
            return [(float(ts), float(pct)) for ts, pct in json.loads(raw)] if raw else []
        except (TypeError, ValueError):
            return []

    async def _record_history(self, proposal: ThorUpgradeProposal):
        """Approval changes in steps (a vote), so only the changes are stored."""
        history = await self.read_history(proposal.name)
        if history and history[-1][1] == proposal.approved_percent:
            return
        history.append((now_ts(), proposal.approved_percent))
        history = history[-self.HISTORY_MAX_POINTS:]
        await self.deps.db.redis.set(self.DB_KEY_HISTORY + proposal.name, json.dumps(history),
                                     ex=int(self.HISTORY_TTL))

    def _progress_cooldown(self, proposal: ThorUpgradeProposal) -> Optional[Cooldown]:
        if self.progress_cd_sec <= 0:
            return None
        return Cooldown(self.deps.db, f'UpgradeProposal:Progress:{proposal.name}', self.progress_cd_sec)

    # ---- outside data ----

    async def _current_block(self) -> int:
        try:
            if self.deps.last_block_cache:
                return int(await self.deps.last_block_cache.get_thor_block() or 0)
        except Exception as e:
            self.logger.warning(f'Failed to get the last block: {e!r}')
        return 0

    async def _get_votes(self, proposal: ThorUpgradeProposal) -> Optional[UpgradeProposalVotes]:
        try:
            nodes = await self.deps.node_cache.get()
            active = [n.node_address for n in nodes.active_nodes]
        except Exception as e:
            self.logger.warning(f'Failed to get active nodes: {e!r}')
            return None
        if not active:
            return None

        approvers = set(proposal.approvers or [])
        rejecters = set(proposal.rejecters or [])
        return UpgradeProposalVotes(
            approvers=[a for a in active if a in approvers],
            not_voted=[a for a in active if a not in approvers and a not in rejecters],
            rejecters=[a for a in active if a in rejecters],
        )

    async def _query_version(self) -> dict:
        if self._version_cache is None:
            try:
                self._version_cache = await self.deps.thor_connector.query_version() or {}
            except Exception as e:
                self.logger.warning(f'Failed to query the version: {e!r}')
                return {}
        return self._version_cache

    async def _current_version(self) -> str:
        return str((await self._query_version()).get('current') or '')

    async def _alert_context(self, proposal: ThorUpgradeProposal) -> dict:
        """Votes, history and the current version: what the alerts with a picture need"""
        return {
            'votes': await self._get_votes(proposal),
            'history': await self.read_history(proposal.name),
            'current_version': await self._current_version(),
        }

    async def _is_version_adopted(self, proposal: ThorUpgradeProposal) -> bool:
        """For a proposal that left the list unapproved by our last look: did the chain switch to it after all?"""
        wanted = parse_proposal_version(proposal.name)
        if not wanted:
            return False
        version = await self._query_version()
        for key in ('current', 'next'):
            v = parse_proposal_version(str(version.get(key) or ''))
            if v and v >= wanted:
                return True
        return False

    # ---- logic ----

    def is_near_quorum(self, p: ThorUpgradeProposal) -> bool:
        return not p.approved and 0 < p.validators_to_quorum <= self.near_quorum_validators

    def _is_progress_update(self, previous: ThorUpgradeProposal, current: ThorUpgradeProposal) -> bool:
        if previous.approved and not current.approved:
            return True  # lost the quorum (validators churned out or changed their votes)
        return abs(current.approved_percent - previous.approved_percent) >= self.min_progress_step_pct

    async def _on_initial_snapshot(self, proposals: Dict[str, ThorUpgradeProposal]):
        for name, p in proposals.items():
            await self._record_history(p)
            await self._mark_announced(self.ANNOUNCED_NEW, name)
            if p.approved:
                await self._mark_announced(self.ANNOUNCED_APPROVED, name)
            if self.is_near_quorum(p):
                await self._mark_announced(self.ANNOUNCED_NEAR_QUORUM, name)
        await self._save_state(proposals)

    async def _handle_live(self, proposal: ThorUpgradeProposal, previous: Optional[ThorUpgradeProposal],
                           block: int):
        name = proposal.name

        if previous is None and self.is_new_proposal_enabled:
            async def make_new():
                return AlertUpgradeProposalNew(proposal, block, **await self._alert_context(proposal))

            await self._announce_once(self.ANNOUNCED_NEW, name, make_new)

        if proposal.approved:
            # once per name, regardless of cooldowns and of the approval flapping later
            if self.is_approved_enabled:
                async def make_approved():
                    return AlertUpgradeProposalApproved(proposal, block, **await self._alert_context(proposal))

                await self._announce_once(self.ANNOUNCED_APPROVED, name, make_approved)
            else:
                await self._mark_announced(self.ANNOUNCED_APPROVED, name)
            return  # more votes after the quorum are no news

        if previous is None or not self.is_progress_update_enabled:
            return

        crossed_near = self.is_near_quorum(proposal) and not await self._was_announced(
            self.ANNOUNCED_NEAR_QUORUM, name)
        if not crossed_near and not self._is_progress_update(previous, proposal):
            return

        cd = self._progress_cooldown(proposal)
        if not crossed_near and cd is not None and not await cd.can_do():
            return

        await self.pass_data_to_listeners(AlertUpgradeProposalProgress(
            previous, proposal, block, near_quorum=self.is_near_quorum(proposal),
            **await self._alert_context(proposal),
        ))
        if crossed_near:
            await self._mark_announced(self.ANNOUNCED_NEAR_QUORUM, name)
        if cd is not None:
            await cd.do()

    async def _handle_gone(self, proposal: ThorUpgradeProposal, block: int) -> bool:
        """Returns True if the proposal is finished, False to keep it in the state."""
        if not block or block <= proposal.height:
            # THORNode deletes a proposal only after its height; empty answer = API glitch
            return False

        name = proposal.name
        if await self._was_announced(self.ANNOUNCED_FINISHED, name):
            return True

        approved = proposal.approved or await self._is_version_adopted(proposal)
        if approved:
            if self.is_approved_enabled:
                async def make_approved():
                    # THORNode has deleted the votes: the last seen ones stay as they were
                    return AlertUpgradeProposalApproved(
                        proposal, block, is_late=True,
                        history=await self.read_history(name),
                        current_version=await self._current_version(),
                    )

                await self._announce_once(self.ANNOUNCED_APPROVED, name, make_approved)
        elif self.is_expired_enabled:
            await self.pass_data_to_listeners(AlertUpgradeProposalExpired(proposal, block))

        await self._mark_announced(self.ANNOUNCED_FINISHED, name)
        return True

    async def on_data(self, sender, data: List[ThorUpgradeProposal]):
        current_state = {p.name: p for p in (data or []) if p.name}
        previous_state = await self._read_prev_state()

        if previous_state is None:
            await self._on_initial_snapshot(current_state)
            return

        block = await self._current_block()
        self._version_cache = None

        for name, proposal in current_state.items():
            await self._record_history(proposal)
            await self._handle_live(proposal, previous_state.get(name), block)

        new_state = dict(current_state)
        for name, proposal in previous_state.items():
            if name not in current_state and not await self._handle_gone(proposal, block):
                new_state[name] = proposal

        await self._save_state(new_state)
