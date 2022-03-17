from dataclasses import dataclass


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

    """
        "averageSlip": "3.924203425934144",
		"endTime": "1647561600",
		"runePriceUSD": "7.91035955539719",
		"startTime": "1647475200",
		"synthMintAverageSlip": "2.8066139468008626",
		"synthMintCount": "1391",
		"synthMintFees": "46439458363",
		"synthMintVolume": "114210025633561",
		"synthRedeemAverageSlip": "2.4380103934669637",
		"synthRedeemCount": "1347",
		"synthRedeemFees": "46030976508",
		"synthRedeemVolume": "100847520551878",
		"toAssetAverageSlip": "3.536127167630058",
		"toAssetCount": "4152",
		"toAssetFees": "205278090708",
		"toAssetVolume": "168324472786321",
		"toRuneAverageSlip": "5.104866346812885",
		"toRuneCount": "4377",
		"toRuneFees": "537687448776",
		"toRuneVolume": "234700531978358",
		"totalCount": "11267",
		"totalFees": "835435974355",
		"totalVolume": "618082550950118"
    """
