from typing import NamedTuple, List

from services.lib.constants import thor_to_float
from services.lib.depcont import DepContainer
from services.lib.logs import WithLogger
from services.lib.midgard.urlgen import free_url_gen


class BorrowerPosition(NamedTuple):
    collateral_asset: str
    collateral_deposited: float
    collateral_withdrawn: float
    debt_issued_tor: float
    debt_repaid_tor: float
    last_open_loan_timestamp: float
    last_repay_loan_timestamp: float
    target_assets: list[str]

    @classmethod
    def from_j(cls, j):
        return cls(
            j['collateral_asset'],
            thor_to_float(j['collateral_deposited']),
            thor_to_float(j['collateral_withdrawn']),
            thor_to_float(j['debt_issued_tor']),
            thor_to_float(j['debt_repaid_tor']),
            float(j['last_open_loan_timestamp']),
            float(j['last_repay_loan_timestamp']),
            j['target_assets']
        )


class BorrowerPositionGenerator(WithLogger):
    def __init__(self, deps: DepContainer):
        self.deps = deps

    async def get_borrower_positions(self, address: str) -> List[BorrowerPosition]:
        path = free_url_gen.url_borrower(address)
        data = await self.deps.midgard_connector.request(path)
        return [BorrowerPosition.from_j(j) for j in data['pools']]
