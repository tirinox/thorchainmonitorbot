from typing import cast

import pytest
from aiohttp import ClientSession

from api.aionode.connector import ThorConnector
from api.aionode.env import ThorEnvironment
from api.aionode.types import ThorUpgradeProposal


SUCCESS_PAYLOAD = [{
    'approved': False,
    'approved_percent': '54.35',
    'approvers': [
        'thor1rp6ll4p2qrj5k9mfelzmwv7ht0gv26pqxka8py',
        'thor1rvjz9xtyjuwf4antkjwsa94v4kctm4smu7alas',
    ],
    'height': 26518000,
    'info': '',
    'name': '3.19.0',
    'validators_to_quorum': 12,
}]


def test_thor_upgrade_proposal_from_json():
    proposal = ThorUpgradeProposal.from_json(SUCCESS_PAYLOAD[0])

    assert proposal.approved is False
    assert proposal.approved_percent == 54.35
    assert proposal.approvers == [
        'thor1rp6ll4p2qrj5k9mfelzmwv7ht0gv26pqxka8py',
        'thor1rvjz9xtyjuwf4antkjwsa94v4kctm4smu7alas',
    ]
    assert proposal.height == 26518000
    assert proposal.info == ''
    assert proposal.name == '3.19.0'
    assert proposal.validators_to_quorum == 12


@pytest.mark.asyncio
async def test_query_upgrade_proposals_returns_typed_response():
    connector = ThorConnector(env=ThorEnvironment(), session=cast(ClientSession, cast(object, None)))
    seen = {}

    async def fake_request(path, **kwargs):
        seen['path'] = path
        seen['kwargs'] = kwargs
        return SUCCESS_PAYLOAD

    connector._request = fake_request

    result = await connector.query_upgrade_proposals()

    assert seen['path'] == '/thorchain/upgrade_proposals'
    assert seen['kwargs'] == {'height': None}
    assert len(result) == 1
    assert isinstance(result[0], ThorUpgradeProposal)
    assert result[0].name == '3.19.0'
    assert result[0].approved_percent == 54.35


@pytest.mark.asyncio
async def test_query_upgrade_proposals_returns_empty_list_on_null():
    connector = ThorConnector(env=ThorEnvironment(), session=cast(ClientSession, cast(object, None)))

    async def fake_request(path, **kwargs):
        return None

    connector._request = fake_request

    result = await connector.query_upgrade_proposals()

    assert result == []

