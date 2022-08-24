from services.lib.memo import THORMemoParsed
from services.models.tx import ThorTxType


def test_memo1():
    memo = \
        '=:ETH.ETH:0xA58818F1cA5A7DD524Eca1F89E2325e15BAD6cc4::::FC4414199:0xd533a949740bb3306d119cc777fa900ba034cd52'
    m = THORMemoParsed.parse_memo(memo)
    assert m.action == ThorTxType.TYPE_SWAP
    assert m.asset == 'ETH.ETH'
    assert m.dex_aggregator_address == 'FC4414199'
    assert m.limit == 0
    assert m.final_asset_address == '0xd533a949740bb3306d119cc777fa900ba034cd52'
    assert m.affiliate_fee == 0
    assert m.affiliate_address == None