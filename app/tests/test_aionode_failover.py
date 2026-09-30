import json

import pytest

from api.aionode.connector import ThorConnector
from api.aionode.env import ThorEnvironment

OWN_NODE = 'http://own-node'
GATEWAY = 'http://gateway'
ARCHIVE = 'http://archive'

POOLS = [{'asset': 'BTC.BTC', 'status': 'Available', 'balance_rune': '100', 'balance_asset': '10'}]

# what the nodes really answer for a height they do not have
PRUNED = (500, '{"code":2,"message":"failed to load state at height 1; no commit info found","details":[]}')
NO_ARCHIVE = (503, 'No archive nodes configured for this chain')
HTML_ERROR = (502, '<html><body>Bad Gateway</body></html>')


class FakeResponse:
    def __init__(self, status, text):
        self.status = status
        self._text = text

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class FakeSession:
    def __init__(self, answers):
        self.answers = answers
        self.asked = []

    def get(self, url, **_kwargs):
        base = next(b for b in self.answers if url.startswith(b))
        self.asked.append(base)
        return FakeResponse(*self.answers[base])


def _connector(answers):
    session = FakeSession(answers)
    envs = [ThorEnvironment(thornode_url=url) for url in answers]
    return ThorConnector(envs[0], session, additional_envs=envs[1:]), session


@pytest.mark.asyncio
@pytest.mark.parametrize('gateway_answer', [NO_ARCHIVE, HTML_ERROR])
async def test_non_json_answer_fails_over_to_the_next_node(gateway_answer):
    connector, session = _connector({
        OWN_NODE: PRUNED,
        GATEWAY: gateway_answer,
        ARCHIVE: (200, json.dumps(POOLS)),
    })

    pools = await connector.query_pools(height=1)

    assert [p.asset for p in pools] == ['BTC.BTC']
    assert session.asked == [OWN_NODE, GATEWAY, ARCHIVE]


@pytest.mark.asyncio
async def test_no_node_has_the_height():
    # None lets PoolCache rebuild the pools from Midgard instead of failing the LP report
    connector, _ = _connector({OWN_NODE: PRUNED, GATEWAY: NO_ARCHIVE})
    assert await connector.query_pools(height=1) is None
