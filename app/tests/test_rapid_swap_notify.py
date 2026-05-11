from typing import cast

import pytest

from jobs.scanner.event_db import EventDatabase
from jobs.scanner.tx import ThorEvent
from lib.db import DB
from lib.depcont import DepContainer
from models.memo import ActionType
from models.tx import ThorAction
from tests.fakes import FakeDB, FakeRedis
from tools.debug.dbg_rapid_swap import RapidSwapCompletedDebugNotifier


class DummyTx:
	def __init__(self, tx_hash: str, action_type: ActionType = ActionType.SWAP):
		self.tx_hash = tx_hash
		self.type = action_type.value if hasattr(action_type, 'value') else str(action_type)

	def is_of_type(self, t):
		if isinstance(t, (tuple, list, set)):
			return any(self.is_of_type(item) for item in t)
		wanted = t.value if hasattr(t, 'value') else str(t)
		return self.type == wanted


def make_deps() -> DepContainer:
	deps = DepContainer()
	deps.db = cast(DB, cast(object, FakeDB(FakeRedis())))
	return deps


def make_swap_event(tx_id: str, height: int, *, pool: str = 'BTC.BTC', stream_count: int = 1, stream_quantity: int = 2):
	return ThorEvent.from_dict({
		'type': 'swap',
		'id': tx_id,
		'pool': pool,
		'swap_target': '0',
		'swap_slip': '0',
		'liquidity_fee': '0',
		'liquidity_fee_in_rune': '0',
		'emit_asset': '1 THOR.RUNE',
		'streaming_swap_quantity': str(stream_quantity),
		'streaming_swap_count': str(stream_count),
		'chain': 'THOR',
		'from': 'thor1from',
		'to': 'thor1to',
		'coin': '100000000 BTC.BTC',
		'memo': 'SWAP:THOR.RUNE:thor1to',
	}, height=height)


async def store_swap_events(deps: DepContainer, tx_id: str, heights: list[int], stream_counts: list[int] | None = None):
	event_db = EventDatabase(deps.db)
	await event_db.write_tx_status_kw(
		tx_id,
		id=tx_id,
		memo='SWAP:THOR.RUNE:thor1to',
		from_address='thor1from',
		out_asset='THOR.RUNE',
	)
	stream_counts = stream_counts or list(range(1, len(heights) + 1))
	for index, height in enumerate(heights, start=1):
		event = make_swap_event(
			tx_id,
			height,
			pool='BTC.BTC' if index % 2 else 'ETH.ETH',
			stream_count=stream_counts[index - 1],
			stream_quantity=max(stream_counts),
		)
		await event_db.write_tx_status(tx_id, {f'ev_swap_{index}': event.attrs})


@pytest.mark.asyncio
async def test_rapid_swap_completed_notifier_plays_short_sound_once_per_new_rapid_swap(monkeypatch):
	deps = make_deps()
	notifier = RapidSwapCompletedDebugNotifier(deps)
	await store_swap_events(deps, 'rapid-1', [100, 100], stream_counts=[60, 61])

	played = []

	async def fake_say(msg: str):
		played.append(msg)

	monkeypatch.setattr('tools.debug.dbg_rapid_swap.say', fake_say)

	tx = cast(ThorAction, cast(object, DummyTx('rapid-1')))
	first = await notifier.on_data(None, [tx])
	second = await notifier.on_data(None, [tx])

	assert first == ['rapid-1']
	assert second == []
	assert played == ['rapid swap']


@pytest.mark.asyncio
async def test_rapid_swap_completed_notifier_skips_swaps_without_saved_blocks(monkeypatch):
	deps = make_deps()
	notifier = RapidSwapCompletedDebugNotifier(deps)
	await store_swap_events(deps, 'normal-1', [100, 100], stream_counts=[60, 60])

	played = []

	async def fake_say(msg: str):
		played.append(msg)

	monkeypatch.setattr('tools.debug.dbg_rapid_swap.say', fake_say)

	tx = cast(ThorAction, cast(object, DummyTx('normal-1')))
	result = await notifier.on_data(None, [tx])

	assert result == []
	assert played == []


@pytest.mark.asyncio
async def test_rapid_swap_completed_notifier_ignores_non_swap_actions(monkeypatch):
	deps = make_deps()
	notifier = RapidSwapCompletedDebugNotifier(deps)
	await store_swap_events(deps, 'rapid-2', [100, 100], stream_counts=[60, 61])

	played = []

	async def fake_say(msg: str):
		played.append(msg)

	monkeypatch.setattr('tools.debug.dbg_rapid_swap.say', fake_say)

	tx = cast(ThorAction, cast(object, DummyTx('rapid-2', action_type=ActionType.WITHDRAW)))
	result = await notifier.on_data(None, [tx])

	assert result == []
	assert played == []


@pytest.mark.asyncio
async def test_rapid_swap_completed_notifier_respects_watched_tx_filter(monkeypatch):
	deps = make_deps()
	notifier = RapidSwapCompletedDebugNotifier(deps, watch_tx_id='WATCHED-TX')
	await store_swap_events(deps, 'WATCHED-TX', [100, 100], stream_counts=[60, 61])
	await store_swap_events(deps, 'OTHER-TX', [100, 100], stream_counts=[60, 61])

	played = []

	async def fake_say(msg: str):
		played.append(msg)

	monkeypatch.setattr('tools.debug.dbg_rapid_swap.say', fake_say)

	other_tx = cast(ThorAction, cast(object, DummyTx('OTHER-TX')))
	watch_tx = cast(ThorAction, cast(object, DummyTx('WATCHED-TX')))

	first = await notifier.on_data(None, [other_tx])
	second = await notifier.on_data(None, [watch_tx])

	assert first == []
	assert second == ['WATCHED-TX']
	assert played == ['rapid swap']


@pytest.mark.asyncio
async def test_rapid_swap_completed_notifier_handles_missing_streaming_fields_gracefully(monkeypatch):
	deps = make_deps()
	notifier = RapidSwapCompletedDebugNotifier(deps)
	event_db = EventDatabase(deps.db)
	await event_db.write_tx_status_kw(
		'missing-stream-fields',
		id='missing-stream-fields',
		memo='SWAP:THOR.RUNE:thor1to',
		from_address='thor1from',
		out_asset='THOR.RUNE',
	)
	base_event = ThorEvent.from_dict({
		'type': 'swap',
		'id': 'missing-stream-fields',
		'pool': 'BTC.BTC',
		'swap_target': '0',
		'swap_slip': '0',
		'liquidity_fee': '0',
		'liquidity_fee_in_rune': '0',
		'emit_asset': '1 THOR.RUNE',
		'chain': 'THOR',
		'from': 'thor1from',
		'to': 'thor1to',
		'coin': '100000000 BTC.BTC',
		'memo': 'SWAP:THOR.RUNE:thor1to',
	}, height=100)
	await event_db.write_tx_status('missing-stream-fields', {'ev_swap_1': base_event.attrs})

	played = []

	async def fake_say(msg: str):
		played.append(msg)

	monkeypatch.setattr('tools.debug.dbg_rapid_swap.say', fake_say)

	tx = cast(ThorAction, cast(object, DummyTx('missing-stream-fields')))
	result = await notifier.on_data(None, [tx])

	assert result == []
	assert played == []


