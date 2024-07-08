from typing import NamedTuple


class TxCountStats(NamedTuple):
    curr: dict[str, int]
    prev: dict[str, int]


class TxMetricType:
    SWAP = 'swap'
    SWAP_SYNTH = 'synth'
    STREAMING = 'streaming'
    ADD_LIQUIDITY = 'add'
    WITHDRAW_LIQUIDITY = 'withdraw'
    TRADE_SWAP = 'trade_swap'
    TRADE_DEPOSIT = 'trade_deposit'
    TRADE_WITHDRAWAL = 'trade_withdrawal'

    @staticmethod
    def usd_key(rune_key):
        return f'{rune_key}_usd'
