from api.aionode.types import ThorLimitSwapsQueue


LIMIT_SWAPS_EXAMPLE = {
    "limit_swaps": [
        {
            "swap": {
                "tx": {
                    "id": "5D6DE0E436A022A9D0711B83754C0F47080E3E964752CE3AA6383E1FB955B544",
                    "chain": "ETH",
                    "memo": "=<:b:bc1qu8xncv4943vdaettuxjhv495we9eds6kq93mma:1000000/100800/0",
                },
                "target_asset": "BTC.BTC",
                "destination": "bc1qu8xncv4943vdaettuxjhv495we9eds6kq93mma",
                "trade_target": "1000000",
                "swap_type": "limit",
                "stream_interval": "100800",
                "state": {
                    "failed_swap_reasons": [
                        "emit asset 997808 less than price limit 1000000"
                    ]
                },
                "version": "v2",
            },
            "ratio": "100000000",
            "blocks_since_created": "27095",
            "time_to_expiry_blocks": "16105",
            "created_timestamp": "0",
        },
        {
            "swap": {
                "tx": {
                    "id": "F88C03BD36035984D1412BBEEFF305981F62B4C8D3F1A03920C1D8D85D985C7D",
                    "chain": "THOR",
                },
                "target_asset": "THOR.RUJI",
                "swap_type": "limit",
            },
            "ratio": "182850000",
            "blocks_since_created": "13548",
            "time_to_expiry_blocks": "852",
            "created_timestamp": "0",
        },
    ],
    "pagination": {
        "offset": "0",
        "limit": "100",
        "total": "2",
        "has_next": False,
        "has_prev": False,
    },
}


def test_parse_limit_swaps_queue_response():
    result = ThorLimitSwapsQueue.from_json(LIMIT_SWAPS_EXAMPLE)

    assert len(result.limit_swaps) == 2
    assert result.limit_swaps[0].ratio == "100000000"
    assert result.limit_swaps[0].swap["target_asset"] == "BTC.BTC"
    assert result.limit_swaps[0].swap["tx"]["chain"] == "ETH"
    assert result.limit_swaps[1].time_to_expiry_blocks == "852"

    assert result.pagination.total == "2"
    assert result.pagination.limit == "100"
    assert result.pagination.has_next is False

