from typing import cast

import pytest
from aiohttp import ClientSession

from api.aionode.connector import ThorConnector
from api.aionode.env import ThorEnvironment
from api.aionode.types import ThorException, ThorMemoReference


REGISTRATION_HASH = 'C757C9EE79A7341817017D0EA714E3CD5C9C366D2C7B1583631046E266A03347'
SUCCESS_PAYLOAD = {
    'asset': 'BTC.BTC',
    'memo': '=:ETH.USDT:0xE9fbf0857a16805535588fd018fb9C2Df1c5b0d5:491625094752/1/0:sto:0',
    'reference': '11791',
    'height': '25621817',
    'registration_hash': REGISTRATION_HASH,
    'registered_by': 'thor1uszfy2dyd2rcjxxpy6wjuv450muljac6ssr70k',
    'used_by_txs': [
        'FFA1DA63BC81E7AEA8D094896739AE3D01FF60034A29E24AB81554C06C36476C',
    ],
}
ERROR_PAYLOAD = {
    'code': 3,
    'message': 'reference memo not found for hash: '
               'C757C9EE79A7341817017D0EA714E3CD5C9C366D2C7B1583631046E266A03341: invalid request',
    'details': [],
}


def test_thor_memo_reference_from_json():
    memo_ref = ThorMemoReference.from_json(SUCCESS_PAYLOAD)

    assert memo_ref.reference == 11791
    assert memo_ref.asset == 'BTC.BTC'
    assert memo_ref.memo == '=:ETH.USDT:0xE9fbf0857a16805535588fd018fb9C2Df1c5b0d5:491625094752/1/0:sto:0'
    assert memo_ref.height == 25621817
    assert memo_ref.registration_hash == REGISTRATION_HASH
    assert memo_ref.registered_by == 'thor1uszfy2dyd2rcjxxpy6wjuv450muljac6ssr70k'
    assert memo_ref.used_by_txs == ['FFA1DA63BC81E7AEA8D094896739AE3D01FF60034A29E24AB81554C06C36476C']


@pytest.mark.asyncio
async def test_query_memo_reference_returns_typed_response():
    connector = ThorConnector(env=ThorEnvironment(), session=cast(ClientSession, cast(object, None)))
    seen = {}

    async def fake_request(path, **kwargs):
        seen['path'] = path
        seen['kwargs'] = kwargs
        return SUCCESS_PAYLOAD

    connector._request = fake_request

    result = await connector.query_memo_reference(REGISTRATION_HASH)

    assert seen['path'] == f'/thorchain/memo/{REGISTRATION_HASH}'
    assert seen['kwargs'] == {}
    assert isinstance(result, ThorMemoReference)
    assert result.reference == 11791
    assert result.height == 25621817
    assert result.used_by_txs == ['FFA1DA63BC81E7AEA8D094896739AE3D01FF60034A29E24AB81554C06C36476C']


@pytest.mark.asyncio
async def test_query_memo_reference_raises_thor_exception_on_error():
    connector = ThorConnector(env=ThorEnvironment(), session=cast(ClientSession, cast(object, None)))

    async def fake_request(path, **kwargs):
        return ERROR_PAYLOAD

    connector._request = fake_request

    with pytest.raises(ThorException) as exc_info:
        await connector.query_memo_reference(REGISTRATION_HASH)

    assert exc_info.value.code == 3
    assert 'reference memo not found for hash' in exc_info.value.message
    assert exc_info.value.details == []

