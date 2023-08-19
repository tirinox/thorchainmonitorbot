class TxType:
    ADD_LIQUIDITY = 'addLiquidity'
    SWAP = 'swap'
    WITHDRAW = 'withdraw'
    DONATE = 'donate'
    REFUND = 'refund'
    SWITCH = 'switch'  # todo: remove

    LOAN_OPEN = 'loan+'
    LOAN_CLOSE = 'loan-'

    LIMIT_ORDER = 'limit_order'
    BOND = 'bond'
    UNBOND = 'unbond'
    LEAVE = 'leave'
    THORNAME = 'thorname'
    OUTBOUND = 'out'

    ALL_EXCEPT_DONATE = ADD_LIQUIDITY, SWAP, WITHDRAW, REFUND, SWITCH
    GROUP_ADD_WITHDRAW = WITHDRAW, ADD_LIQUIDITY
