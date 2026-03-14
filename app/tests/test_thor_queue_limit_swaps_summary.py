from api.aionode.types import ThorLimitSwapsSummary


SUMMARY_EXAMPLE = {
    "total_limit_swaps": "2",
    "total_value_usd": "547863536442",
    "asset_pairs": [
        {
            "source_asset": "ETH.WBTC-0X2260FAC5E5542A773AA44FBCFEDF7C193BC2C599",
            "target_asset": "BTC.BTC",
            "count": "1",
            "total_value_usd": "356811922050"
        },
        {
            "source_asset": "THOR.RUNE",
            "target_asset": "THOR.RUJI",
            "count": "1",
            "total_value_usd": "191051614392"
        }
    ],
    "oldest_swap_blocks": "27265",
    "average_age_blocks": "20491"
}


def test_parse_limit_swaps_summary():
    s = ThorLimitSwapsSummary.from_json(SUMMARY_EXAMPLE)
    assert s.total_limit_swaps == "2"
    assert s.total_value_usd == "547863536442"
    assert len(s.asset_pairs) == 2
    assert s.asset_pairs[0].source_asset.startswith("ETH.WBTC")
    assert s.asset_pairs[1].target_asset == "THOR.RUJI"
    assert s.oldest_swap_blocks == "27265"
    assert s.average_age_blocks == "20491"

