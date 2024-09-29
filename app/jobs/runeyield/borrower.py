from dataclasses import dataclass
from typing import NamedTuple, List, Dict

from api.aionode.types import ThorBorrowerPosition
from api.midgard.urlgen import free_url_gen
from lib.constants import thor_to_float, LOAN_MARKER
from lib.date_utils import now_ts
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.price import LastPriceHolder


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
    collateral_price_last_add: float

    @property
    def collateral_current_usd(self):
        return self.price_holder.convert_to_usd(self.details.t_pos.collateral_current, self.pool)

    @property
    def last_open_loan_timestamp(self):
        return self.details.m_pos.last_open_loan_timestamp

    @property
    def last_repay_loan_timestamp(self):
        return self.details.m_pos.last_repay_loan_timestamp

    @property
    def collateral_ratio(self):
        try:
            return self.collateral_current_usd / self.details.t_pos.debt_current
        except ZeroDivisionError:
            return 0.0

    @property
    def loan_to_value(self):
        try:
            return self.details.t_pos.debt_current / self.collateral_current_usd * 100.0
        except ZeroDivisionError:
            return 0.0

    @property
    def time_elapsed(self):
        return now_ts() - self.last_open_loan_timestamp


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

        last_open_block = -1
        try:
            last_open_block = t_pos.last_open_height
            pools = await self.deps.pool_fetcher.load_pools(height=last_open_block)
            lph = self.deps.price_holder.clone()
            lph.update(pools)
            collateral_price_last_add = lph.convert_to_usd(1.0, t_pos.asset)
        except Exception as e:
            self.logger.error(f"Could not get collateral price at last open height ({last_open_block}): {e}")
            collateral_price_last_add = 0.0

        return LoanReportCard(
            pool=(t_pos.asset if t_pos else pool),
            address=address,
            details=BorrowerPair(m_pos, t_pos),
            price_holder=self.deps.price_holder,
            collateral_price_last_add=collateral_price_last_add
        )
