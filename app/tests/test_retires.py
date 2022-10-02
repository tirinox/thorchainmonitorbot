import pytest

from services.lib.utils import retries, TooManyTriesException


@pytest.mark.asyncio
async def test_reties():
    n = 1

    @retries(5)
    async def will_pass():
        nonlocal n
        if n < 3:
            n += 1
            raise ValueError('fail')
        return True

    assert await will_pass()

    with pytest.raises(TooManyTriesException):
        n = -10
        await will_pass()

    with pytest.raises(TooManyTriesException):
        n = 1
        will_pass.times = 1
        await will_pass()

    n = 1
    will_pass.times = 100
    await will_pass()
