import json
from typing import Dict, List, Optional

from api.aionode.types import ThorUpgradeProposal
from lib.cooldown import Cooldown
from lib.date_utils import parse_timespan_to_seconds
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.upgrade_proposal import AlertUpgradeProposalNew, AlertUpgradeProposalProgress


class UpgradeProposalsNotifier(INotified, WithDelegates, WithLogger):
    DB_KEY_LAST_STATE = 'UpgradeProposals:LastState'

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

    @staticmethod
    def proposal_key(proposal: ThorUpgradeProposal) -> str:
        return f'{proposal.height}:{proposal.name}'

    async def _read_prev_state(self) -> Optional[Dict[str, ThorUpgradeProposal]]:
        raw_data = await self.deps.db.redis.get(self.DB_KEY_LAST_STATE)
        if raw_data is None:
            return None
        try:
            data = json.loads(raw_data)
            return {
                key: ThorUpgradeProposal.from_json(item)
                for key, item in data.items()
            }
        except (TypeError, ValueError, AttributeError):
            return None

    async def _save_state(self, proposals: List[ThorUpgradeProposal]):
        data = {
            self.proposal_key(proposal): proposal._asdict()
            for proposal in proposals
        }
        await self.deps.db.redis.set(self.DB_KEY_LAST_STATE, json.dumps(data))

    def _is_progress_update(self, previous: ThorUpgradeProposal, current: ThorUpgradeProposal) -> bool:
        if previous.approved != current.approved:
            return True

        return abs(current.approved_percent - previous.approved_percent) >= self.min_progress_step_pct

    async def _progress_cooldown(self, proposal: ThorUpgradeProposal) -> Optional[Cooldown]:
        if self.progress_cd_sec <= 0:
            return None
        return Cooldown(self.deps.db, f'UpgradeProposal:Progress:{self.proposal_key(proposal)}', self.progress_cd_sec)

    async def on_data(self, sender, data: List[ThorUpgradeProposal]):
        proposals = data or []
        current_state = {
            self.proposal_key(proposal): proposal
            for proposal in proposals
        }
        previous_state = await self._read_prev_state()

        if previous_state is None:
            await self._save_state(proposals)
            return

        if self.is_new_proposal_enabled:
            for key, proposal in current_state.items():
                if key not in previous_state:
                    await self.pass_data_to_listeners(AlertUpgradeProposalNew(proposal))

        if self.is_progress_update_enabled:
            for key, proposal in current_state.items():
                previous = previous_state.get(key)
                if previous and self._is_progress_update(previous, proposal):
                    cd = await self._progress_cooldown(proposal)
                    if cd is None or await cd.can_do():
                        await self.pass_data_to_listeners(AlertUpgradeProposalProgress(previous, proposal))
                        if cd is not None:
                            await cd.do()

        await self._save_state(proposals)


