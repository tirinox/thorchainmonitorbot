from dataclasses import dataclass
from typing import List


@dataclass
class SwapsHistoryEntry:
    average_slip: float
    end_time: int
    rune_price_usd: float
    start_time: int
    synth_mint_average_slip: float
    synth_mint_count: int
    synth_mint_fees: int
    synth_mint_volume: int
    synth_redeem_average_slip: float
    synth_redeem_count: int
    synth_redeem_fees: int
    synth_redeem_volume: int
    to_asset_average_slip: float
    to_asset_count: int
    to_asset_fees: int
    to_asset_volume: int
    to_rune_average_slip: float
    to_rune_count: int
    to_rune_fees: int
    to_rune_volume: int
    total_count: int
    total_fees: int
    total_volume: int

    @classmethod
    def from_json(cls, j):
        return cls(
            average_slip=float(j.get('averageSlip', 0)),
            end_time=int(j.get('endTime', 0)),
            rune_price_usd=float(j.get('runePriceUSD', 0)),
            start_time=int(j.get('startTime', 0)),
            synth_mint_average_slip=float(j.get('synthMintAverageSlip', 0)),
            synth_mint_count=int(j.get('synthMintCount', 0)),
            synth_mint_fees=int(j.get('synthMintFees', 0)),
            synth_mint_volume=int(j.get('synthMintVolume', 0)),
            synth_redeem_average_slip=float(j.get('synthRedeemAverageSlip', 0)),
            synth_redeem_count=int(j.get('synthRedeemCount', 0)),
            synth_redeem_fees=int(j.get('synthRedeemFees', 0)),
            synth_redeem_volume=int(j.get('synthRedeemVolume', 0)),
            to_asset_average_slip=float(j.get('toAssetAverageSlip', 0)),
            to_asset_count=int(j.get('toAssetCount', 0)),
            to_asset_fees=int(j.get('toAssetFees', 0)),
            to_asset_volume=int(j.get('toAssetVolume', 0)),
            to_rune_average_slip=float(j.get('toRuneAverageSlip', 0)),
            to_rune_count=int(j.get('toRuneCount', 0)),
            to_rune_fees=int(j.get('toRuneFees', 0)),
            to_rune_volume=int(j.get('toRuneVolume', 0)),
            total_count=int(j.get('totalCount', 0)),
            total_fees=int(j.get('totalFees', 0)),
            total_volume=int(j.get('totalVolume', 0)),
        )


@dataclass
class SwapHistoryResponse:
    intervals: List[SwapsHistoryEntry]
    meta: SwapsHistoryEntry

    @classmethod
    def from_json(cls, j):
        return cls(
            meta=SwapsHistoryEntry.from_json(j.get('meta', {})),
            intervals=[SwapsHistoryEntry.from_json(interval_j) for interval_j in j.get('intervals', [])]
        )
