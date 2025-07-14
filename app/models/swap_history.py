from dataclasses import dataclass
from typing import List

from lib.money import non_zero_f


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
    to_asset_volume_usd: int
    to_rune_volume_usd: int
    to_trade_volume_usd: int
    from_trade_volume_usd: int
    to_secured_volume_usd: int
    from_secured_volume_usd: int
    synth_mint_volume_usd: int
    synth_redeem_volume_usd: int
    total_volume_usd: int

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

            to_asset_volume_usd=int(j.get('toAssetVolumeUSD', 0)),
            to_rune_volume_usd=int(j.get('toRuneVolumeUSD', 0)),
            to_trade_volume_usd=int(j.get('toTradeVolumeUSD', 0)),
            from_trade_volume_usd=int(j.get('fromTradeVolumeUSD', 0)),
            to_secured_volume_usd=int(j.get('toSecuredVolumeUSD', 0)),
            from_secured_volume_usd=int(j.get('fromSecuredVolumeUSD', 0)),
            synth_mint_volume_usd=int(j.get('synthMintVolumeUSD', 0)),
            synth_redeem_volume_usd=int(j.get('synthRedeemVolumeUSD', 0)),
            total_volume_usd=int(j.get('totalVolumeUSD', 0)),

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

    def __add__(self, other: 'SwapsHistoryEntry'):
        return SwapsHistoryEntry(
            start_time=non_zero_f(self.start_time, other.start_time, min),
            end_time=non_zero_f(self.end_time, other.end_time, max),
            rune_price_usd=max(self.rune_price_usd, other.rune_price_usd),

            to_asset_count=self.to_asset_count + other.to_asset_count,
            to_rune_count=self.to_rune_count + other.to_rune_count,
            to_trade_count=self.to_trade_count + other.to_trade_count,
            from_trade_count=self.from_trade_count + other.from_trade_count,
            to_secured_count=self.to_secured_count + other.to_secured_count,
            from_secured_count=self.from_secured_count + other.from_secured_count,
            synth_mint_count=self.synth_mint_count + other.synth_mint_count,
            synth_redeem_count=self.synth_redeem_count + other.synth_redeem_count,
            total_count=self.total_count + other.total_count,

            to_asset_volume=self.to_asset_volume + other.to_asset_volume,
            to_rune_volume=self.to_rune_volume + other.to_rune_volume,
            to_trade_volume=self.to_trade_volume + other.to_trade_volume,
            from_trade_volume=self.from_trade_volume + other.from_trade_volume,
            to_secured_volume=self.to_secured_volume + other.to_secured_volume,
            from_secured_volume=self.from_secured_volume + other.from_secured_volume,
            synth_mint_volume=self.synth_mint_volume + other.synth_mint_volume,
            synth_redeem_volume=self.synth_redeem_volume + other.synth_redeem_volume,
            total_volume=self.total_volume + other.total_volume,

            to_asset_volume_usd=self.to_asset_volume_usd + other.to_asset_volume_usd,
            to_rune_volume_usd=self.to_rune_volume_usd + other.to_rune_volume_usd,
            to_trade_volume_usd=self.to_trade_volume_usd + other.to_trade_volume_usd,
            from_trade_volume_usd=self.from_trade_volume_usd + other.from_trade_volume_usd,
            to_secured_volume_usd=self.to_secured_volume_usd + other.to_secured_volume_usd,
            from_secured_volume_usd=self.from_secured_volume_usd + other.from_secured_volume_usd,
            synth_mint_volume_usd=self.synth_mint_volume_usd + other.synth_mint_volume_usd,
            synth_redeem_volume_usd=self.synth_redeem_volume_usd + other.synth_redeem_volume_usd,
            total_volume_usd=self.total_volume_usd + other.total_volume_usd,

            to_asset_fees=self.to_asset_fees + other.to_asset_fees,
            to_rune_fees=self.to_rune_fees + other.to_rune_fees,
            to_trade_fees=self.to_trade_fees + other.to_trade_fees,
            from_trade_fees=self.from_trade_fees + other.from_trade_fees,
            to_secured_fees=self.to_secured_fees + other.to_secured_fees,
            from_secured_fees=self.from_secured_fees + other.from_secured_fees,
            synth_mint_fees=self.synth_mint_fees + other.synth_mint_fees,
            synth_redeem_fees=self.synth_redeem_fees + other.synth_redeem_fees,
            total_fees=self.total_fees + other.total_fees,

            to_asset_average_slip=self.to_asset_average_slip + other.to_asset_average_slip,
            to_rune_average_slip=self.to_rune_average_slip + other.to_rune_average_slip,
            to_trade_average_slip=self.to_trade_average_slip + other.to_trade_average_slip,
            from_trade_average_slip=self.from_trade_average_slip + other.from_trade_average_slip,
            to_secured_average_slip=self.to_secured_average_slip + other.to_secured_average_slip,
            from_secured_average_slip=self.from_secured_average_slip + other.from_secured_average_slip,
            synth_mint_average_slip=self.synth_mint_average_slip + other.synth_mint_average_slip,
            synth_redeem_average_slip=self.synth_redeem_average_slip + other.synth_redeem_average_slip,
            average_slip=self.average_slip + other.average_slip,
        )


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
                if interval_j.get('totalCount', '0') != '0'
            ]
        )

    @property
    def last_whole_interval(self) -> SwapsHistoryEntry:
        return self.intervals[-2] if self.intervals[-1].total_count == 0 else self.intervals[-1]

    def sum_of_intervals(self, start, end):
        if start >= end:
            return SwapsHistoryEntry.zero()
        return sum(self.intervals[start + 1:end], start=self.intervals[start])

    def curr_and_prev_interval(self):
        middle = len(self.intervals) // 2
        interval_prev = self.sum_of_intervals(0, middle)
        interval_curr = self.sum_of_intervals(middle, len(self.intervals))
        return interval_curr, interval_prev
