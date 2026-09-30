from types import SimpleNamespace

import pytest

from jobs.scanner.arb_detector import ArbBotDetector, ArbStatus
from tests.fakes import FakeDB

BOT = 'thor14mh37ua4vkyur0l5ra297a4la6tmf95mt96a55'
HUMAN = 'thor1edd07q7q00hcjm5jg404g5jf84fuexqe93txsj'


class FakeThorConnector:
    def __init__(self, sequences):
        self.sequences = sequences  # address -> sequence, or None when THORNode fails
        self.queries = []

    async def query_raw(self, path):
        address = path.rsplit('/', 1)[-1]
        self.queries.append(address)
        sequence = self.sequences.get(address)
        return None if sequence is None else {'account': {'address': address, 'sequence': str(sequence)}}


class FakeNameCache:
    def __init__(self):
        self.names = {}

    async def save_custom_name(self, name, address, expiring=True):
        self.names[address] = name

    async def save_name_list(self, address, names, expiring=True):
        pass


def _detector(sequences):
    deps = SimpleNamespace(
        cfg=SimpleNamespace(as_int=lambda _key, default=None: default),
        db=FakeDB(),
        thor_connector=FakeThorConnector(sequences),
        name_service=SimpleNamespace(cache=FakeNameCache()),
    )
    return ArbBotDetector(deps)


@pytest.mark.asyncio
async def test_new_arb_bot_is_recognized_on_its_first_swap():
    detector = _detector({BOT: 250_000})

    assert await detector.try_to_detect_arb_bot(BOT) == ArbStatus.ARB
    assert await detector.try_to_detect_arb_bot(BOT) == ArbStatus.ARB
    assert detector.deps.thor_connector.queries == [BOT]  # the second answer comes from Redis
    assert detector.deps.name_service.cache.names[BOT] == 'Arb-Bot-6a55'


@pytest.mark.asyncio
async def test_ordinary_address():
    detector = _detector({HUMAN: 12})
    assert await detector.try_to_detect_arb_bot(HUMAN) == ArbStatus.NOT_ARB
    assert await detector.read_arb_status(HUMAN) == ArbStatus.NOT_ARB


@pytest.mark.asyncio
async def test_failed_query_is_not_remembered():
    detector = _detector({BOT: None})
    assert await detector.try_to_detect_arb_bot(BOT) == ArbStatus.UNKNOWN
    assert await detector.read_arb_status(BOT) == ArbStatus.UNKNOWN  # not NOT_ARB for a week

    detector.deps.thor_connector.sequences[BOT] = 250_000
    assert await detector.try_to_detect_arb_bot(BOT) == ArbStatus.ARB


@pytest.mark.asyncio
async def test_not_a_thor_address():
    detector = _detector({})
    assert await detector.try_to_detect_arb_bot('bc1qjnejnaytae55pjpktuqyugdj9el298xafl0tva') == ArbStatus.NOT_ARB
    assert detector.deps.thor_connector.queries == []
