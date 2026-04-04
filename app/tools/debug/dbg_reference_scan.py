import argparse
import asyncio
from dataclasses import dataclass

from jobs.ref_memo_cache import RefMemoCache
from jobs.scanner.block_result import BlockResult
from jobs.scanner.scan_cache import BlockScannerCached
from lib.date_utils import format_date
from models.memo import ActionType, THORMemo

DEFAULT_BLOCKS_BACK = 5_000
DEFAULT_STRIDE = 1
PROGRESS_EVERY = 100


@dataclass
class ReferenceMemoHit:
    block_no: int
    block_ts: float
    source: str
    tx_ref: str
    memo: str
    reference_memo: str

    @property
    def block_time_str(self) -> str:
        return format_date(self.block_ts) if self.block_ts else 'n/a'


def parse_reference_memo(memo: str):
    if not memo:
        return None

    try:
        parsed = THORMemo.parse_memo(memo, no_raise=True)
    except Exception:
        return None

    if parsed and parsed.action == ActionType.REFERENCE:
        return parsed
    return None


def find_reference_hits_in_block(block: BlockResult, include_observed=True) -> list[ReferenceMemoHit]:
    hits = []

    for tx in block.txs:
        parsed = parse_reference_memo(tx.memo)
        if parsed:
            hits.append(ReferenceMemoHit(
                block_no=block.block_no,
                block_ts=block.timestamp,
                source='native',
                tx_ref=tx.tx_hash,
                memo=tx.memo,
                reference_memo=parsed.reference_memo,
            ))

    if include_observed:
        for tx in block.all_observed_txs:
            parsed = parse_reference_memo(tx.memo)
            if parsed:
                direction = 'in' if tx.is_inbound else 'out'
                hits.append(ReferenceMemoHit(
                    block_no=block.block_no,
                    block_ts=block.timestamp,
                    source=f'observed_{direction}',
                    tx_ref=tx.tx_id,
                    memo=tx.memo,
                    reference_memo=parsed.reference_memo,
                ))

    return hits


def print_hit(hit: ReferenceMemoHit):
    print(f'[{hit.source}] block #{hit.block_no:,} @ {hit.block_time_str}')
    print(f'  tx: {hit.tx_ref}')
    print(f'  memo: {hit.memo}')
    print(f'  reference_memo: {hit.reference_memo}')
    print()


async def resolve_block_range(app, start_block=None, end_block=None, blocks_back=DEFAULT_BLOCKS_BACK):
    current_block = await app.deps.last_block_cache.get_thor_block()

    if start_block is None:
        start_block = max(0, current_block - max(1, int(blocks_back)))
        if end_block is None:
            end_block = current_block
    elif end_block is None:
        end_block = start_block

    if start_block < 0 or end_block < 0:
        raise ValueError(f'Block numbers must be non-negative, got {start_block=} {end_block=}')
    if end_block < start_block:
        raise ValueError(f'end_block must be >= start_block, got {start_block=} {end_block=}')

    return current_block, start_block, end_block


async def dbg_scan_reference_memos(app, start_block=None, end_block=None,
                                   blocks_back=DEFAULT_BLOCKS_BACK,
                                   stride=DEFAULT_STRIDE,
                                   include_observed=True,
                                   stop_on_first=False):
    current_block, start_block, end_block = await resolve_block_range(
        app,
        start_block=start_block,
        end_block=end_block,
        blocks_back=blocks_back,
    )
    stride = max(1, int(stride))

    scanner = BlockScannerCached(app.deps, last_block=start_block, stride=stride)
    ref_memo_cache = RefMemoCache(app.deps)
    ref_memo_cache._dedup.ignore_all_checks = True

    print('>>> Reference memo scan')
    print(f'    current block     : {current_block:,}')
    print(f'    start block       : {start_block:,}')
    print(f'    end block         : {end_block:,}')
    print(f'    stride            : {stride:,}')
    print(f'    include_observed  : {include_observed}')
    print(f'    stop_on_first     : {stop_on_first}')
    print()

    total_blocks = 0
    total_hits = 0

    for block_no in range(start_block, end_block + 1, stride):
        block = await scanner.fetch_one_block(block_no)
        total_blocks += 1

        if block is None:
            print(f'[{block_no:,}] no block data returned')
            continue

        if block.is_error:
            print(f'[{block_no:,}] scanner error: {block.error.code} {block.error.message}')
            continue

        await ref_memo_cache.on_data(scanner, block)

        hits = find_reference_hits_in_block(block, include_observed=include_observed)
        if hits:
            total_hits += len(hits)
            print(f'>>> block #{block_no:,} produced {len(hits)} reference memo hit(s)')
            for hit in hits:
                print_hit(hit)
            if stop_on_first:
                break

        if total_blocks % PROGRESS_EVERY == 0:
            print(f'... scanned {total_blocks:,} blocks; hits so far: {total_hits:,}')

    print('>>> Done')
    print(f'    scanned blocks : {total_blocks:,}')
    print(f'    total hits     : {total_hits:,}')


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Scan historical THORChain blocks for txs whose memo parses as ActionType.REFERENCE.',
    )
    parser.add_argument('--start-block', type=int, default=None,
                        help='First block to scan. If omitted, uses current tip minus --blocks-back.')
    parser.add_argument('--end-block', type=int, default=None,
                        help='Last block to scan, inclusive. If omitted and --start-block is set, scans one block.')
    parser.add_argument('--blocks-back', type=int, default=DEFAULT_BLOCKS_BACK,
                        help=f'How far back from current tip to start when --start-block is omitted. Default: {DEFAULT_BLOCKS_BACK}.')
    parser.add_argument('--stride', type=int, default=DEFAULT_STRIDE,
                        help=f'Scan every Nth block. Default: {DEFAULT_STRIDE}.')
    parser.add_argument('--native-only', action='store_true',
                        help='Scan only native THORChain tx memos and skip observed tx memos.')
    parser.add_argument('--stop-on-first', action='store_true',
                        help='Stop scanning as soon as the first REFERENCE memo is found.')
    return parser


async def run(args=None):
    from tools.lib.lp_common import LpAppFramework

    parser = build_arg_parser()
    args = parser.parse_args(args=args)

    app = LpAppFramework()
    async with app:
        await dbg_scan_reference_memos(
            app,
            start_block=args.start_block,
            end_block=args.end_block,
            blocks_back=args.blocks_back,
            stride=args.stride,
            include_observed=not args.native_only,
            stop_on_first=args.stop_on_first,
        )


if __name__ == '__main__':
    asyncio.run(run())

