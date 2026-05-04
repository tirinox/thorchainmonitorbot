import asyncio
import json
import os

from jobs.limit_recorder import LimitSwapStatsRecorder
from jobs.scanner.limit_detector import LimitSwapDetector
from jobs.scanner.native_scan import BlockScanner
from lib.texts import sep
from lib.utils import recursive_asdict
from models.asset import Asset
from models.memo import THORMemo
from tools.lib.lp_common import LpAppFramework

DEFAULT_TX_ID = 'FBC189BA4B8500F70B7673BE374709AE06EDAE8491D8B6723360518EF114EE22'
DEFAULT_SCAN_BACK_BLOCKS = 6


def _norm_tx_id(tx_id: str) -> str:
	return str(tx_id or '').strip().upper()


def _to_int(value, default: int = 0) -> int:
	try:
		return int(value)
	except (TypeError, ValueError):
		return default


def _to_plain(obj):
	return recursive_asdict(obj, add_properties=True, handle_datetime=True)


def _pretty_dump(obj) -> str:
	return json.dumps(_to_plain(obj), indent=2, sort_keys=True, ensure_ascii=False, default=str)


def _print_dump(title: str, obj):
	sep(title)
	print(_pretty_dump(obj))


def _candidate_heights(tx_details: dict | None, tx_simple: dict | None, scan_back_blocks: int) -> list[int]:
	anchors = []

	for payload in (tx_details, tx_simple):
		if not isinstance(payload, dict):
			continue
		for key in ('consensus_height', 'finalised_height', 'finalized_height', 'block_height', 'height'):
			if height := _to_int(payload.get(key)):
				anchors.append(height)

	heights = []
	for anchor in anchors:
		heights.extend([anchor, anchor - 1, anchor + 1])
		for offset in range(2, scan_back_blocks + 1):
			heights.append(anchor - offset)

	result = []
	seen = set()
	for height in heights:
		if height <= 0 or height in seen:
			continue
		seen.add(height)
		result.append(height)
	return result


def _find_matches(block, tx_id: str):
	tx_id = _norm_tx_id(tx_id)
	matches = []

	for tx in block.txs:
		if _norm_tx_id(tx.tx_hash) != tx_id:
			continue
		parsed = LimitSwapDetector._make_opened_limit_swap_from_native_tx(tx)
		kind = 'native_deposit' if parsed else 'native_tx'
		matches.append((kind, tx, parsed))

	for tx in block.all_observed_txs:
		if _norm_tx_id(tx.tx_id) != tx_id:
			continue
		parsed = LimitSwapDetector._make_opened_limit_swap_from_observed_tx(tx, block.block_no)
		kind = 'observed_inbound' if parsed else 'observed_tx'
		matches.append((kind, tx, parsed))

	return matches


async def _print_match(app: LpAppFramework, block, kind: str, raw_tx, opened_limit_swap):
	ph = await app.deps.pool_cache.get()
	recorder = LimitSwapStatsRecorder(app.deps)

	memo_str = str(getattr(raw_tx, 'memo', '') or '')
	parsed_memo = THORMemo.parse_memo(memo_str, no_raise=True) if memo_str else None
	memo_asset = str(parsed_memo.asset or '') if parsed_memo else ''
	fuzzy_asset = ph.pool_fuzzy_first(memo_asset, restore_type=True) if memo_asset else ''

	sep(f'Match in block {block.block_no}: {kind}')
	print(f'Block timestamp: {block.timestamp}')
	print(f'Raw memo: {memo_str!r}')
	if parsed_memo:
		print(f'Parsed memo action: {parsed_memo.action.value}')
		print(f'Parsed memo asset: {memo_asset!r}')
		if memo_asset:
			print(f'Fuzzy-resolved memo asset: {fuzzy_asset!r}')
			try:
				print(f'Asset.from_string(memo.asset): {str(Asset.from_string(memo_asset))!r}')
			except Exception as e:
				print(f'Asset.from_string(memo.asset) failed: {e!r}')
	else:
		print('Parsed memo: <failed>')

	_print_dump('Raw transaction object', raw_tx)

	if parsed_memo:
		_print_dump('Parsed THORMemo', parsed_memo)

	if opened_limit_swap:
		_print_dump('OpenedLimitSwap from LimitSwapDetector', opened_limit_swap)
		resolved_meta = recorder._build_open_meta(opened_limit_swap, block.block_no, block.timestamp, ph)
		_print_dump('OpenLimitSwapMeta from LimitSwapStatsRecorder', resolved_meta)
	else:
		print('LimitSwapDetector did not classify this tx as an opened limit swap in this representation.')


async def dbg_limit_tx(app: LpAppFramework, tx_id: str = DEFAULT_TX_ID, scan_back_blocks: int = DEFAULT_SCAN_BACK_BLOCKS):
	tx_id = _norm_tx_id(tx_id)
	print(f'Looking up tx: {tx_id}')

	details_result, simple_result = await asyncio.gather(
		app.deps.thor_connector.query_tx_details(tx_id),
		app.deps.thor_connector.query_tx_simple(tx_id),
		return_exceptions=True,
	)

	tx_details = None if isinstance(details_result, Exception) else details_result
	tx_simple = None if isinstance(simple_result, Exception) else simple_result

	if isinstance(details_result, Exception):
		print(f'query_tx_details failed: {details_result!r}')
	elif tx_details is not None:
		_print_dump('query_tx_details', tx_details)

	if isinstance(simple_result, Exception):
		print(f'query_tx_simple failed: {simple_result!r}')
	elif tx_simple is not None:
		_print_dump('query_tx_simple', tx_simple)

	candidate_heights = _candidate_heights(tx_details, tx_simple, scan_back_blocks)
	if not candidate_heights:
		print('Could not derive any candidate heights from tx details/simple response.')
		return False

	print(f'Candidate heights to inspect: {candidate_heights}')

	scanner = BlockScanner(app.deps, role='debug')
	found_any = False

	for height in candidate_heights:
		sep(f'Fetch block {height}')
		block = await scanner.fetch_one_block(height)
		if not block:
			print('No block returned.')
			continue

		matches = _find_matches(block, tx_id)
		print(
			f'Block {height}: {len(block.txs)} native txs, '
			f'{len(block.all_observed_txs)} observed txs, '
			f'{len(matches)} direct matches for tx id.'
		)

		for kind, raw_tx, opened_limit_swap in matches:
			found_any = True
			await _print_match(app, block, kind, raw_tx, opened_limit_swap)

	if not found_any:
		sep('Result')
		print('Tx was not found in the inspected blocks, or it did not parse as a limit swap there.')
		print('Try increasing SCAN_BACK_BLOCKS or inspect the heights from query_tx_details/query_tx_simple output.')
		return False

	return True


async def run():
	tx_id = os.environ.get('TXID', DEFAULT_TX_ID)
	scan_back_blocks = _to_int(os.environ.get('SCAN_BACK_BLOCKS'), DEFAULT_SCAN_BACK_BLOCKS)

	app = LpAppFramework()
	async with app:
		await dbg_limit_tx(app, tx_id=tx_id, scan_back_blocks=scan_back_blocks)


if __name__ == '__main__':
	asyncio.run(run())

