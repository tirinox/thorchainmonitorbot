from dataclasses import dataclass
from typing import NamedTuple, List, Dict

from aionode.types import ThorBorrowerPosition
from services.lib.constants import thor_to_float, LOAN_MARKER
from services.lib.depcont import DepContainer
from services.lib.logs import WithLogger
from services.lib.midgard.urlgen import free_url_gen
from services.models.price import LastPriceHolder


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


class BorrowerPair(NamedTuple):
    m_pos: BorrowerPosition
    t_pos: ThorBorrowerPosition

    @property
    def current_collateral(self):
        return self.t_pos.collateral_current

    @property
    def collateral_asset(self):
        return self.m_pos.collateral_asset


@dataclass
class BorrowerFullState:
    positions: Dict[str, BorrowerPair]

    @property
    def get_non_empty_positions(self):
        return [p for p in self.positions.values() if p.current_collateral > 0]


@dataclass
class LoanReportCard:
    pool: str
    address: str
    details: BorrowerPair
    price_holder: LastPriceHolder


class BorrowerPositionGenerator(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    async def get_borrower_positions_midgard(self, address: str) -> List[BorrowerPosition]:
        path = free_url_gen.url_borrower(address)
        data = await self.deps.midgard_connector.request(path)
        return [BorrowerPosition.from_j(j) for j in data['pools']]

    async def _get_borrower_thornode(self, pool: str, address: str):
        return await self.deps.thor_connector.query_borrower_details(pool, address)

    async def get_full_borrower_state(self, address: str) -> BorrowerFullState:
        m_positions = await self.get_borrower_positions_midgard(address)

        pos_map = {}

        for m_pos in m_positions:
            t_pos = await self._get_borrower_thornode(m_pos.collateral_asset, address)
            pos_map[m_pos.collateral_asset] = BorrowerPair(m_pos, t_pos)

        return BorrowerFullState(pos_map)

    async def get_loan_report_card(self, pool: str, address: str) -> LoanReportCard:
        if pool.startswith(LOAN_MARKER):
            pool = pool[len(LOAN_MARKER):]

        m_positions = await self.get_borrower_positions_midgard(address)
        m_pos = next((p for p in m_positions if p.collateral_asset == pool), None)

        if not m_pos:
            raise ValueError(f'No position for {pool} found for address {address}')

        t_pos = await self._get_borrower_thornode(pool, address)

        return LoanReportCard(
            pool, address,
            BorrowerPair(m_pos, t_pos),
            self.deps.price_holder
        )
