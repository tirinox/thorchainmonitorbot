from dataclasses import dataclass


@dataclass
class PoolMemberDetails:
    asset_added: int = 0
    asset_withdrawn: int = 0
    asset_address: str = ''
    asset_deposit: int = 0
    asset_pending: int = 0

    rune_added: int = 0
    rune_withdrawn: int = 0
    rune_address: str = ''
    rune_deposit: int = 0
    rune_pending: int = 0

    date_first_added: int = 0
    date_last_added: int = 0
    liquidity_units: int = 0
    pool: str = ''

    @classmethod
    def from_json(cls, j):
        return cls(

            asset_added=int(j.get('assetAdded', 0)),
            asset_address=j.get('assetAddress', ''),
            asset_withdrawn=int(j.get('assetWithdrawn', 0)),
            asset_deposit=int(j.get('assetDeposit', 0)),
            asset_pending=int(j.get('assetPending', 0)),
            date_first_added=int(j.get('dateFirstAdded', 0)),
            date_last_added=int(j.get('dateLastAdded', 0)),
            liquidity_units=int(j.get('liquidityUnits', 0)),
            pool=j.get('pool', ''),
            rune_added=int(j.get('runeAdded', 0)),
            rune_withdrawn=int(j.get('runeWithdrawn', 0)),
            rune_address=j.get('runeAddress', ''),
            rune_deposit=int(j.get('runeDeposit', 0)),
            rune_pending=int(j.get('runePending', 0)),
        )
