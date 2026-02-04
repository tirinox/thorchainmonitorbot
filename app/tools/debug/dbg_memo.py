import asyncio

from models.memo import THORMemo, ActionType


async def dbg_memo_reference():
    memo = "REFERENCE:BTC.BTC:=:ETH.USDC:0x39eeb9f03078f5af3484820ea45a61c9374f7f57:177222558447/3/0:sto:0"
    m = THORMemo.parse_memo(memo)
    print(m)
    assert m.action == ActionType.REFERENCE
    assert m.reference_memo == "BTC.BTC:=:ETH.USDC:0x39eeb9f03078f5af3484820ea45a61c9374f7f57:177222558447/3/0:sto:0"

    memo2 = "R:433434334"
    m2 = THORMemo.parse_memo(memo2)
    print(m2)
    assert m2.action == ActionType.USE_REFERENCE
    assert m2.reference_memo == "433434334"

    memo_limit = "=<:ETH.USDC:0x39eeb9f03078f5af3484820ea45a61c9374f7f57:177222558447/3/0:sto:0"
    m_limit = THORMemo.parse_memo(memo_limit)
    print(m_limit)
    assert m_limit.action == ActionType.LIMIT_ORDER


async def main():
    await dbg_memo_reference()


if __name__ == "__main__":
    asyncio.run(main())
