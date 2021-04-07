from dataclasses import dataclass


@dataclass
class PoolMemberDetails:
    asset_added: int = 0
    asset_withdrawn: int = 0
    asset_address: str = ''

    rune_added: int = 0
    rune_withdrawn: int = 0
    run_address: str = ''

    date_first_added: int = 0
    date_last_added: int = 0
    liquidity_units: int = 0
    pool: str = ''
