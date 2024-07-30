from typing import NamedTuple


class SwapRouteEntry(NamedTuple):
    from_asset: str
    to_asset: str
    volume_rune: float
