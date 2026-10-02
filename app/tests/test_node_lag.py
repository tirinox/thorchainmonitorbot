"""
Our THORNode was down and then lagged behind on 2 Oct 2026 (02:30-02:32 UTC), while the backup node was fine.
The bot got the streaming swap 000000001BB5F1A0... from the backup node, asked our node for its details,
got "tx doesn't exist" and crashed on it. The block scanner, asking our node for a block it did not have yet,
jumped to the chain tip once the node came back and skipped blocks #28065192-28065206.
"""
from types import SimpleNamespace

import pytest

from api.aionode.connector import ThorConnector
from api.aionode.env import ThorEnvironment
from jobs.fetch.stream_watchlist import StreamingSwapStartDetectorFromList
from jobs.scanner.native_scan import BlockScanner
from lib.depcont import DepContainer
from models.s_swap import StreamingSwap, EventChangedStreamingSwapList, AlertSwapStart
from tests.fakes import FakeDB, FakePubSubRedis, make_price_holder

TX_ID = '000000001BB5F1A0EA4AE2E5CD230B7C0D89F2FDA32BE95C175C5AA78D6E11A2'

NOT_FOUND = {
    'code': 3,
    'message': f"tx: {TX_ID} doesn't exist: invalid request",
    'details': [],
}

TX_DETAILS = {
    'tx_id': TX_ID,
    'tx': {
        'tx': {
            'id': TX_ID,
            'chain': 'THOR',
            'from_address': 'thor14mh37ua4vkyur0l5ra297a4la6tmf95mt96a55',
            'to_address': 'thor1g98cy3n9mmjrpn0sxmn63lztelera37n8n67c0',
            'coins': [{'asset': 'BTC~BTC', 'amount': '18386046'}],
            'gas': None,
            'memo': '=:ETH~ETH:thor14mh37ua4vkyur0l5ra297a4la6tmf95mt96a55:576126976/0/3',
        },
        'status': 'done',
    },
    'consensus_height': 28065203,
    'finalised_height': 28065205,
}

FUTURE_BLOCK = {
    'code': 2,
    'message': 'cannot query with height in the future; please provide a valid height: invalid height',
    'details': [],
}


def _connector(primary_answer, backup_answer):
    connector = ThorConnector(ThorEnvironment(thornode_url='http://ours'), session=None,
                              additional_envs=[ThorEnvironment(thornode_url='http://backup')])
    asked = []

    def fake_request(name, answer):
        async def request(path, is_rpc=False, height=None):
            asked.append(name)
            return answer

        return request

    connector._clients[0].request = fake_request('ours', primary_answer)
    connector._clients[1].request = fake_request('backup', backup_answer)
    return connector, asked


@pytest.mark.asyncio
async def test_tx_details_asks_backup_when_our_node_has_no_tx():
    connector, asked = _connector(NOT_FOUND, TX_DETAILS)
    assert await connector.query_tx_details(TX_ID) == TX_DETAILS
    assert asked == ['ours', 'backup']


@pytest.mark.asyncio
async def test_tx_details_none_when_no_node_has_tx():
    connector, asked = _connector(NOT_FOUND, NOT_FOUND)
    assert await connector.query_tx_details(TX_ID) is None
    assert asked == ['ours', 'backup']


class Listener:
    def __init__(self):
        self.events = []

    async def on_data(self, sender, data):
        self.events.append(data)


def _detector(details):
    deps = DepContainer()
    deps.pool_cache = SimpleNamespace(get=_async_value(make_price_holder()))
    deps.thor_connector = SimpleNamespace(query_tx_details=_async_value(details))
    deps.emergency = SimpleNamespace(report=lambda *args, **kwargs: pytest.fail(f'emergency: {args} {kwargs}'))
    detector = StreamingSwapStartDetectorFromList(deps)
    listener = Listener()
    detector.add_subscriber(listener)
    return detector, listener


def _async_value(value):
    async def get(*args, **kwargs):
        return value

    return get


def _new_swap():
    swap = StreamingSwap(tx_id=TX_ID, interval=0, quantity=3, source_asset='BTC~BTC', target_asset='ETH~ETH')
    return EventChangedStreamingSwapList(new_swaps=[swap], completed_swaps=[])


@pytest.mark.parametrize('details', [None, NOT_FOUND])
@pytest.mark.asyncio
async def test_swap_start_without_tx_details_is_skipped(details):
    detector, listener = _detector(details)
    await detector.on_data(None, _new_swap())
    assert listener.events == []


@pytest.mark.asyncio
async def test_swap_start_from_tx_details():
    detector, listener = _detector(TX_DETAILS)
    await detector.on_data(None, _new_swap())

    [alert] = listener.events
    assert isinstance(alert, AlertSwapStart)
    assert alert.tx_id == TX_ID
    assert alert.from_address == 'thor14mh37ua4vkyur0l5ra297a4la6tmf95mt96a55'
    assert alert.in_amount_float == pytest.approx(0.18386046)
    assert alert.block_height == 28065203
    assert alert.quantity == 3


class FakeScannerConnector:
    async def query_thorchain_block_raw(self, height):
        return FUTURE_BLOCK  # our node is stuck at #28065191

    async def query_native_status_raw(self):
        # the chain tip by the time our node is back
        return {'result': {'sync_info': {'latest_block_height': '28065207'}}}


@pytest.mark.asyncio
async def test_scanner_waits_for_block_our_node_does_not_have_yet():
    deps = DepContainer()
    deps.db = FakeDB(FakePubSubRedis())
    deps.thor_connector = FakeScannerConnector()
    scanner = BlockScanner(deps, last_block=28065192)
    scanner._refresh_thor_block_for_state = _async_value(None)

    await scanner.fetch()
    assert scanner.last_block == 28065192
