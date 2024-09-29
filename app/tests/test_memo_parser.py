import pytest

from models.memo import THORMemo, ActionType, is_action


def test_memo1():
    m = THORMemo.parse_memo('=:ETH.ETH:0xA58818F1cA5A7DD524Eca1F89E2325e15BAD6cc4:'
                            ':'
                            ':'
                            ':FC4414199:0xd533a949740bb3306d119cc777fa900ba034cd52')
    assert m.action == ActionType.SWAP
    assert m.asset == 'ETH.ETH'
    assert m.dex_aggregator_address == 'FC4414199'
    assert m.limit == 0
    assert m.final_asset_address == '0xd533a949740bb3306d119cc777fa900ba034cd52'
    assert m.affiliate_fee_bp == 0
    assert m.affiliate_address == ''
    assert m.s_swap_quantity == 1
    assert m.s_swap_interval == 0

    m = THORMemo.parse_memo('SWAP:BTC/BTC:thorname')
    assert m.action == ActionType.SWAP
    assert m.asset == 'BTC/BTC'
    assert m.dex_aggregator_address == ''
    assert m.final_asset_address == ''
    assert m.dest_address == 'thorname'
    assert m.limit == 0
    assert m.s_swap_quantity == 1
    assert m.s_swap_interval == 0

    m = THORMemo.parse_memo('SWAP:AVAX.AVAX:0x12345678901234589012345:18000000/5/20:t:50')
    assert m.action == ActionType.SWAP
    assert m.asset == 'AVAX.AVAX'
    assert m.dest_address == '0x12345678901234589012345'
    assert m.limit == 18000000
    assert m.s_swap_interval == 5
    assert m.s_swap_quantity == 20
    assert m.affiliate_address == 't'
    assert m.affiliate_fee_0_1 == 0.005

    m = THORMemo.parse_memo('trade-:bc1qp8278yutn09r2wu3jrc8xg2a7hgdgwv2gvsdyw')
    assert m.action == ActionType.TRADE_ACC_WITHDRAW
    assert m.dest_address == 'bc1qp8278yutn09r2wu3jrc8xg2a7hgdgwv2gvsdyw'

    m = THORMemo.parse_memo('trade+:thor1g6pnmnyeg48yc3lg796plt0uw50qpp7humfggz')
    assert m.action == ActionType.TRADE_ACC_DEPOSIT
    assert m.dest_address == 'thor1g6pnmnyeg48yc3lg796plt0uw50qpp7humfggz'


def test_memo2():
    memo = 's:e:bob::::822:D1C:1'
    m = THORMemo.parse_memo(memo)
    print(m)


@pytest.mark.parametrize('x, y, result', [
    (ActionType.ADD_LIQUIDITY, ActionType.ADD_LIQUIDITY, True),
    ('', False, False),
    ('DONATE', 'dOnaTe', True),
    (ActionType.DONATE, 'foo', False),
    ('foo', ActionType.DONATE, False),
    (ActionType.DONATE, ActionType.DONATE, True),
    (ActionType.SWAP, ActionType.SWAP, True),
    ('SWAP', 'swap', True),
    ('SWAP', ActionType.SWAP, True),
    (ActionType.SWAP, 'swap', True),
    (ActionType.SWAP, ActionType.ADD_LIQUIDITY, False),
    (ActionType.ADD_LIQUIDITY, ActionType.SWAP, False),
    (ActionType.WITHDRAW, 'withdraw', True),
    ('withdraw', ActionType.WITHDRAW, True),
    (ActionType.SWAP, '', False),
    (ActionType.SWAP, None, False),
    ('', ActionType.SWAP, False),
    (None, ActionType.SWAP, False),
    ('foo', 'bar', False),
    ('refund', [ActionType.SWAP, ActionType.REFUND, ActionType.WITHDRAW], True),
    ('REFUND', (ActionType.SWAP, ActionType.REFUND, ActionType.WITHDRAW), True),
    (ActionType.REFUND, {ActionType.SWAP, ActionType.REFUND, ActionType.WITHDRAW}, True),
    ('refund', [ActionType.SWAP, ActionType.WITHDRAW], False),
    (ActionType.TRADE_ACC_WITHDRAW, [ActionType.TRADE_ACC_WITHDRAW, 'swap'], True),
    (ActionType.TRADE_ACC_WITHDRAW, [ActionType.SWAP, 'trade-'], True),
])
def test_action_type(x, y, result):
    assert is_action(x, y) == result
