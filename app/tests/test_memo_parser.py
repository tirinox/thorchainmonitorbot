from services.lib.memo import THORMemo
from services.models.tx import ThorTxType


def test_memo1():
    m = THORMemo.parse_memo('=:ETH.ETH:0xA58818F1cA5A7DD524Eca1F89E2325e15BAD6cc4:'
                                  ':'
                                  ':'
                                  ':FC4414199:0xd533a949740bb3306d119cc777fa900ba034cd52')
    assert m.action == ThorTxType.TYPE_SWAP
    assert m.asset == 'ETH.ETH'
    assert m.dex_aggregator_address == 'FC4414199'
    assert m.limit == 0
    assert m.final_asset_address == '0xd533a949740bb3306d119cc777fa900ba034cd52'
    assert m.affiliate_fee == 0
    assert m.affiliate_address is None
    assert m.s_swap_quantity == 0
    assert m.s_swap_interval == 0

    m = THORMemo.parse_memo('SWAP:BTC/BTC:thorname')
    assert m.action == ThorTxType.TYPE_SWAP
    assert m.asset == 'BTC/BTC'
    assert m.dex_aggregator_address is None
    assert m.final_asset_address is None
    assert m.dest_address == 'thorname'
    assert m.limit == 0
    assert m.s_swap_quantity == 0
    assert m.s_swap_interval == 0

    m = THORMemo.parse_memo('SWAP:AVAX.AVAX:0x12345678901234589012345:18000000/5/20:t:50')
    assert m.action == ThorTxType.TYPE_SWAP
    assert m.asset == 'AVAX.AVAX'
    assert m.dest_address == '0x12345678901234589012345'
    assert m.limit == 18000000
    assert m.s_swap_interval == 5
    assert m.s_swap_quantity == 20
    assert m.affiliate_address == 't'
    assert m.affiliate_fee == 0.005


def test_memo2():
    memo = 's:e:bob::::822:D1C:1'
    m = THORMemo.parse_memo(memo)
    print(m)
