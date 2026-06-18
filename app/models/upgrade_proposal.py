from typing import NamedTuple

from api.aionode.types import ThorUpgradeProposal


class AlertUpgradeProposalNew(NamedTuple):
    proposal: ThorUpgradeProposal


class AlertUpgradeProposalProgress(NamedTuple):
    previous: ThorUpgradeProposal
    current: ThorUpgradeProposal

