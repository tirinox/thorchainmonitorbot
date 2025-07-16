from dataclasses import dataclass
from typing import List


def from_e2(x):
    return int(x) / 1e2


@dataclass
class SwapsHistoryEntry:
    start_time: int
    end_time: int
    rune_price_usd: float

    # Counts
    to_asset_count: int
    to_rune_count: int
    to_trade_count: int
    from_trade_count: int
    to_secured_count: int
    from_secured_count: int
    synth_mint_count: int
    synth_redeem_count: int
    total_count: int

    # Volumes
    to_asset_volume: int
    to_rune_volume: int
    to_trade_volume: int
    from_trade_volume: int
    to_secured_volume: int
    from_secured_volume: int
    synth_mint_volume: int
    synth_redeem_volume: int
    total_volume: int

    # USD Volumes
    to_asset_volume_usd: float
    to_rune_volume_usd: float
    to_trade_volume_usd: float
    from_trade_volume_usd: float
    to_secured_volume_usd: float
    from_secured_volume_usd: float
    synth_mint_volume_usd: float
    synth_redeem_volume_usd: float
    total_volume_usd: float

    # Fees
    to_asset_fees: int
    to_rune_fees: int
    to_trade_fees: int
    from_trade_fees: int
    to_secured_fees: int
    from_secured_fees: int
    synth_mint_fees: int
    synth_redeem_fees: int
    total_fees: int

    # Average slips
    to_asset_average_slip: float
    to_rune_average_slip: float
    to_trade_average_slip: float
    from_trade_average_slip: float
    to_secured_average_slip: float
    from_secured_average_slip: float
    synth_mint_average_slip: float
    synth_redeem_average_slip: float
    average_slip: float

    @classmethod
    def from_json(cls, j):
        return cls(
            start_time=int(j.get('startTime', 0)),
            end_time=int(j.get('endTime', 0)),
            rune_price_usd=float(j.get('runePriceUSD', 0)),

            to_asset_count=int(j.get('toAssetCount', 0)),
            to_rune_count=int(j.get('toRuneCount', 0)),
            to_trade_count=int(j.get('toTradeCount', 0)),
            from_trade_count=int(j.get('fromTradeCount', 0)),
            to_secured_count=int(j.get('toSecuredCount', 0)),
            from_secured_count=int(j.get('fromSecuredCount', 0)),
            synth_mint_count=int(j.get('synthMintCount', 0)),
            synth_redeem_count=int(j.get('synthRedeemCount', 0)),
            total_count=int(j.get('totalCount', 0)),

            to_asset_volume=int(j.get('toAssetVolume', 0)),
            to_rune_volume=int(j.get('toRuneVolume', 0)),
            to_trade_volume=int(j.get('toTradeVolume', 0)),
            from_trade_volume=int(j.get('fromTradeVolume', 0)),
            to_secured_volume=int(j.get('toSecuredVolume', 0)),
            from_secured_volume=int(j.get('fromSecuredVolume', 0)),
            synth_mint_volume=int(j.get('synthMintVolume', 0)),
            synth_redeem_volume=int(j.get('synthRedeemVolume', 0)),
            total_volume=int(j.get('totalVolume', 0)),

            to_asset_volume_usd=from_e2(j.get('toAssetVolumeUSD', 0)),
            to_rune_volume_usd=from_e2(j.get('toRuneVolumeUSD', 0)),
            to_trade_volume_usd=from_e2(j.get('toTradeVolumeUSD', 0)),
            from_trade_volume_usd=from_e2(j.get('fromTradeVolumeUSD', 0)),
            to_secured_volume_usd=from_e2(j.get('toSecuredVolumeUSD', 0)),
            from_secured_volume_usd=from_e2(j.get('fromSecuredVolumeUSD', 0)),
            synth_mint_volume_usd=from_e2(j.get('synthMintVolumeUSD', 0)),
            synth_redeem_volume_usd=from_e2(j.get('synthRedeemVolumeUSD', 0)),
            total_volume_usd=from_e2(j.get('totalVolumeUSD', 0)),

            to_asset_fees=int(j.get('toAssetFees', 0)),
            to_rune_fees=int(j.get('toRuneFees', 0)),
            to_trade_fees=int(j.get('toTradeFees', 0)),
            from_trade_fees=int(j.get('fromTradeFees', 0)),
            to_secured_fees=int(j.get('toSecuredFees', 0)),
            from_secured_fees=int(j.get('fromSecuredFees', 0)),
            synth_mint_fees=int(j.get('synthMintFees', 0)),
            synth_redeem_fees=int(j.get('synthRedeemFees', 0)),
            total_fees=int(j.get('totalFees', 0)),

            to_asset_average_slip=float(j.get('toAssetAverageSlip', 0)),
            to_rune_average_slip=float(j.get('toRuneAverageSlip', 0)),
            to_trade_average_slip=float(j.get('toTradeAverageSlip', 0)),
            from_trade_average_slip=float(j.get('fromTradeAverageSlip', 0)),
            to_secured_average_slip=float(j.get('toSecuredAverageSlip', 0)),
            from_secured_average_slip=float(j.get('fromSecuredAverageSlip', 0)),
            synth_mint_average_slip=float(j.get('synthMintAverageSlip', 0)),
            synth_redeem_average_slip=float(j.get('synthRedeemAverageSlip', 0)),
            average_slip=float(j.get('averageSlip', 0)),
        )

    @classmethod
    def zero(cls):
        return cls.from_json({})


def sum_by_attribute(entries, attr: str):
    return sum(getattr(entry, attr, 0) for entry in entries) if entries else 0


@dataclass
class SwapHistoryResponse:
    intervals: List[SwapsHistoryEntry]
    meta: SwapsHistoryEntry

    @classmethod
    def from_json(cls, j):
        return cls(
            meta=SwapsHistoryEntry.from_json(j.get('meta', {})),
            intervals=[
                SwapsHistoryEntry.from_json(interval_j)
                for interval_j in j.get('intervals', [])
            ]
        )

    @property
    def last_whole_interval(self) -> SwapsHistoryEntry:
        return self.intervals[-2] if self.intervals[-1].total_count == 0 else self.intervals[-1]

    def curr_and_prev_interval(self, attr_name):
        middle = len(self.intervals) // 2
        interval_prev = sum_by_attribute(self.intervals[0:middle], attr_name)
        interval_curr = sum_by_attribute(self.intervals[middle:], attr_name)
        return interval_curr, interval_prev

    @property
    def with_last_day_dropped(self):
        return SwapHistoryResponse(
            intervals=self.intervals[:-1],
            meta=self.meta
        )
