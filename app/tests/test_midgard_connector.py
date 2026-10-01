import aiohttp
import pytest

from api.midgard.connector import MidgardConnector, MidgardError, MidgardNotFound, MidgardBadResponse
from api.midgard.name_service import THORNameAPIClient


class FakeResponse:
    def __init__(self, status=200, payload=None, text=''):
        self.status = status
        self._payload = payload
        self._text = text

    async def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeSession:
    """Answers with the given responses in turn; an exception in the list is raised by get()."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.urls = []

    def get(self, url, headers=None):
        self.urls.append(url)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def make_connector(*responses, retries=3):
    session = FakeSession(*responses)
    return MidgardConnector(session, retries, public_url='https://midgard.test/', retry_delay=0), session


@pytest.mark.asyncio
async def test_ok():
    mdg, session = make_connector(FakeResponse(payload={'a': 1}))
    assert await mdg.request('/v2/health') == {'a': 1}
    assert session.urls == ['https://midgard.test/v2/health']


@pytest.mark.asyncio
async def test_not_found_is_an_exception_and_is_not_retried():
    mdg, session = make_connector(FakeResponse(404), FakeResponse(payload={}))
    with pytest.raises(MidgardNotFound):
        await mdg.request('/v2/thorname/lookup/nobody')
    assert len(session.urls) == 1


@pytest.mark.asyncio
async def test_temporary_failures_are_retried():
    mdg, session = make_connector(
        FakeResponse(502, text='Bad Gateway'),
        aiohttp.ClientConnectionError('reset'),
        FakeResponse(payload=[1, 2]),
    )
    assert await mdg.request('/v2/pools') == [1, 2]
    assert len(session.urls) == 3


@pytest.mark.asyncio
async def test_gives_up_after_all_tries():
    mdg, session = make_connector(FakeResponse(503), FakeResponse(503), FakeResponse(503), FakeResponse(payload={}))
    with pytest.raises(MidgardBadResponse) as e:
        await mdg.request('/v2/pools')
    assert e.value.status == 503
    assert len(session.urls) == 3


@pytest.mark.asyncio
async def test_bad_request_is_not_retried():
    mdg, session = make_connector(FakeResponse(400, text='bad interval'), FakeResponse(payload={}))
    with pytest.raises(MidgardBadResponse):
        await mdg.request('/v2/history/swaps?interval=eon')
    assert len(session.urls) == 1


@pytest.mark.asyncio
async def test_not_json_is_a_midgard_error():
    mdg, _ = make_connector(FakeResponse(payload=ValueError('not json')), retries=1)
    with pytest.raises(MidgardError):
        await mdg.request('/v2/health')


@pytest.mark.asyncio
async def test_queries_turn_not_found_into_empty_values_but_not_failures():
    mdg, _ = make_connector(FakeResponse(404))
    assert await mdg.query_pool_membership('thor1nobody') == []

    mdg, _ = make_connector(FakeResponse(404))
    assert await mdg.query_pool('NO.POOL') is None

    # "Midgard is down" must not look like "this address has no pools"
    mdg, _ = make_connector(FakeResponse(500), retries=1)
    with pytest.raises(MidgardError):
        await mdg.query_pool_membership('thor1somebody')

    # 404 used to reach the parser as a string
    mdg, _ = make_connector(FakeResponse(404))
    with pytest.raises(MidgardNotFound):
        await mdg.query_earnings(count=1, interval='day')


@pytest.mark.asyncio
async def test_thorname_client_shows_no_name_when_midgard_fails():
    mdg, _ = make_connector(FakeResponse(404))
    assert await THORNameAPIClient(mdg).thorname_lookup('nobody') is None

    mdg, _ = make_connector(FakeResponse(500), retries=1)
    assert await THORNameAPIClient(mdg).thorname_reversed_lookup('thor1x') == []

    mdg, _ = make_connector(FakeResponse(payload=['alice', 'bob']))
    assert await THORNameAPIClient(mdg).get_thornames_owned_by_address('thor1x') == ['alice', 'bob']
