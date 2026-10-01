import json
from typing import NamedTuple, Optional


class TokenRecord(NamedTuple):
    address: str
    chain_id: int
    decimals: int
    name: str
    symbol: str
    logoURI: str


CONTRACT_DATA_BASE_PATH = './data/token_list'

# Where the data of a DEX aggregator leg came from
DEX_SOURCE_MEMO = 'memo'  # the swap memo (aggregator + final token are known, the amount is not)
DEX_SOURCE_CHAIN = 'chain'  # decoded from the EVM transaction (amount and recipient are known)
DEX_SOURCE_MEMO_AND_CHAIN = 'memo+chain'  # memo data enriched with on-chain data


class AmountToken(NamedTuple):
    """
    One leg of a DEX-aggregated swap: either the swap-in (an external token is swapped into the L1 gas asset
    before entering THORChain) or the swap-out (the L1 gas asset is swapped into an external token after
    leaving THORChain).
    Everything except "amount" and "token" may be unknown, so consumers must be ready for None/'' values.
    """
    amount: Optional[float]  # None = unknown (e.g. the outbound has not been broadcast yet)
    token: Optional[TokenRecord]  # None = the token could not be resolved; see "token_address" then
    aggr_name: str = ''  # human-readable aggregator name or a shortened address when unknown
    aggr_address: str = ''  # aggregator contract address as we saw it (may be shortened if it came from a memo)
    token_address: str = ''  # external token address as we saw it (may be shortened if it came from a memo)
    chain: str = ''  # L1 chain (ETH, AVAX, BSC, BASE)
    source: str = ''  # DEX_SOURCE_*
    recipient: str = ''  # final recipient of the swap-out (from the on-chain call), '' when unknown

    @property
    def has_amount(self) -> bool:
        return self.amount is not None and self.amount > 0

    @property
    def symbol(self) -> str:
        if self.token and self.token.symbol:
            return self.token.symbol
        if self.token_address:
            return short_address(self.token_address)
        return '?'

    @property
    def is_known(self) -> bool:
        """The leg carries at least one meaningful fact: a token or an aggregator."""
        return bool(self.token or self.token_address or self.aggr_name or self.aggr_address)

    def merge_on_chain(self, other: 'AmountToken') -> 'AmountToken':
        """
        Enrich this (memo-based) leg with facts decoded from the chain: the amount, the recipient,
        and a full token/aggregator when the memo had only shortened addresses.
        """
        if not other:
            return self
        return self._replace(
            amount=other.amount if other.amount is not None else self.amount,
            token=other.token or self.token,
            aggr_name=self.aggr_name or other.aggr_name,
            aggr_address=other.aggr_address or self.aggr_address,
            token_address=other.token_address or self.token_address,
            chain=self.chain or other.chain,
            recipient=other.recipient or self.recipient,
            source=DEX_SOURCE_MEMO_AND_CHAIN if self.source != other.source else self.source,
        )

    @property
    def as_json(self):
        return {
            'amount': self.amount,
            'aggr_name': self.aggr_name,
            'aggr_address': self.aggr_address,
            'symbol': self.token.symbol if self.token else '',
            'token_address': self.token_address or (self.token.address if self.token else ''),
            'chain': self.chain,
            'source': self.source,
            'recipient': self.recipient,
        }

    @classmethod
    def from_json(cls, j):
        if isinstance(j, str):
            try:
                j = json.loads(j)
            except json.JSONDecodeError:
                j = None
        if not j or not isinstance(j, dict):
            return

        try:
            amount = float(j.get('amount') or 0.0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0.0:
            amount = None  # unknown

        token_symbol = j.get('symbol', '') or ''
        token_address = j.get('token_address', '') or ''
        token = TokenRecord(token_address, 0, 18, token_symbol, token_symbol, '') if token_symbol else None

        record = cls(
            amount=amount,
            token=token,
            aggr_name=j.get('aggr_name', '') or '',
            aggr_address=j.get('aggr_address', '') or '',
            token_address=token_address,
            chain=j.get('chain', '') or '',
            source=j.get('source', '') or '',
            recipient=j.get('recipient', '') or '',
        )
        return record if record.is_known else None


def short_address(address: str, head=6, tail=4) -> str:
    address = str(address or '')
    if len(address) <= head + tail + 1:
        return address
    return f'{address[:head]}…{address[-tail:]}'


class SwapInOut(NamedTuple):
    swap_in: Optional[AmountToken] = None
    swap_out: Optional[AmountToken] = None

    @property
    def any(self) -> bool:
        return bool(self.swap_in) or bool(self.swap_out)
