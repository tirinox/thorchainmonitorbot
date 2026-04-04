from typing import cast

import pytest
from aiohttp import ClientSession

from api.aionode.connector import ThorConnector
from api.aionode.env import ThorEnvironment
from api.aionode.types import ThorException, ThorMemoCheck


ASSET = 'BTC.BTC'
AMOUNT = 11791
OCCUPIED_PAYLOAD = {
    'reference': '11794',
    'available': False,
    'expires_at': '25628612',
    'usage_count': '0',
    'max_use': '1',
    'can_register': False,
    'memo': '=:l:ltc1q26p4zgvh8cjfrx6xs3dvgnv503xczed9dnscne:929176436/1/0:sto:0',
}
EMPTY_PAYLOAD = {
    'reference': '11791',
    'available': True,
    'expires_at': '0',
    'usage_count': '1',
    'max_use': '1',
    'can_register': True,
    'memo': '',
}
ERROR_PAYLOAD = {
    'code': 3,
    'message': 'memo check failed: invalid request',
    'details': [],
}


def test_thor_memo_check_from_json_for_occupied_reference():
    memo_check = ThorMemoCheck.from_json(OCCUPIED_PAYLOAD)

    assert memo_check.reference == 11794
    assert memo_check.available is False
    assert memo_check.expires_at == 25628612
    assert memo_check.usage_count == 0
    assert memo_check.max_use == 1
    assert memo_check.can_register is False
    assert memo_check.memo == '=:l:ltc1q26p4zgvh8cjfrx6xs3dvgnv503xczed9dnscne:929176436/1/0:sto:0'


def test_thor_memo_check_from_json_for_empty_reference():
    memo_check = ThorMemoCheck.from_json(EMPTY_PAYLOAD)

    assert memo_check.reference == 11791
    assert memo_check.available is True
    assert memo_check.expires_at == 0
    assert memo_check.usage_count == 1
    assert memo_check.max_use == 1
    assert memo_check.can_register is True
    assert memo_check.memo == ''


@pytest.mark.asyncio
async def test_query_memo_check_returns_typed_response():
    connector = ThorConnector(env=ThorEnvironment(), session=cast(ClientSession, cast(object, None)))
    seen = {}

    async def fake_request(path, **kwargs):
        seen['path'] = path
        seen['kwargs'] = kwargs
        return OCCUPIED_PAYLOAD

    connector._request = fake_request

    result = await connector.query_memo_check(ASSET, AMOUNT)

    assert seen['path'] == f'/thorchain/memo/check/{ASSET}/{AMOUNT}'
    assert seen['kwargs'] == {}
    assert isinstance(result, ThorMemoCheck)
    assert result.reference == 11794
    assert result.available is False
    assert result.can_register is False


@pytest.mark.asyncio
async def test_query_memo_check_raises_thor_exception_on_error():
    connector = ThorConnector(env=ThorEnvironment(), session=cast(ClientSession, cast(object, None)))

    async def fake_request(path, **kwargs):
        return ERROR_PAYLOAD

    connector._request = fake_request

    with pytest.raises(ThorException) as exc_info:
        await connector.query_memo_check(ASSET, AMOUNT)

    assert exc_info.value.code == 3
    assert 'memo check failed' in exc_info.value.message
    assert exc_info.value.details == []

