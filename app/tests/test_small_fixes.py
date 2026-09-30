import pytest

from api.aionode.types import ThorNetwork
from lib.date_utils import parse_timespan_to_seconds
from lib.flagship import Flagship
from models.mimir import MimirVoting, MimirVoteOption, super_majority_votes
from models.node_info import NodeInfo
from tests.fakes import FakeDB


@pytest.mark.parametrize('span', ['1min', 'm', '5x', '1h 30', '1..2h'])
def test_bad_timespan_raises(span):
    with pytest.raises(ValueError):
        parse_timespan_to_seconds(span)


@pytest.mark.asyncio
async def test_reading_a_flag_does_not_write_its_value_back():
    db = FakeDB()
    flagship = Flagship(db)
    name = 'a:b'

    assert await flagship.is_flag_set(name) is True  # created with the default value
    stored = await db.redis.get(flagship.key(name))

    assert await flagship.is_flag_set(name) is True
    assert await db.redis.get(flagship.key(name)) == stored  # the access is recorded elsewhere
    assert (await flagship.get_flag_object(name)).last_access_ts > 0

    await flagship.set_flag(name, False)
    assert await flagship.is_flag_set(name) is False

    await flagship.delete_flag(name)
    assert await db.redis.hget(flagship.DB_KEY_ACCESS, name) is None


def test_thor_network_without_bond_reward():
    assert ThorNetwork.from_json({}).bond_reward_rune == 0
    assert ThorNetwork.from_json({'bond_reward_rune': '123'}).bond_reward_rune == 123


def test_bond_provider_of_node_with_zero_bond():
    bp = NodeInfo._make_bond_provider({'bond': '0', 'bond_address': 'thor1'}, 0.0, 0.1, 'thor1', 10.0)
    assert bp.bond_share == 0.0


@pytest.mark.parametrize('nodes, votes, passed', [
    (99, 66, True), (99, 65, False), (100, 66, False), (100, 67, True), (3, 2, True), (1, 1, True),
])
def test_mimir_super_majority(nodes, votes, passed):
    voting = MimirVoting('KEY', {1: MimirVoteOption(1, votes)}, nodes)
    assert voting.passed is passed
    assert voting.top_options[0].need_votes_to_pass == abs(super_majority_votes(nodes) - votes)
    assert (voting.top_options[0].need_votes_to_pass == 0) is (votes == super_majority_votes(nodes))
