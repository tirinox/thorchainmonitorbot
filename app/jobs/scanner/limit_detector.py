from typing import List, NamedTuple

from jobs.scanner.block_result import BlockResult
from jobs.scanner.tx import NativeThorTx, ThorEvent
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.memo import ActionType, THORMemo


class ClosedLimitSwap(NamedTuple):
    event: ThorEvent
    reason: str = ''

    @property
    def txid(self) -> str:
        attrs = self.event.attrs if isinstance(self.event.attrs, dict) else {}
        return str(attrs.get('txid') or '')


class LimitSwapBlockUpdate(NamedTuple):
    block_no: int
    timestamp: int
    new_opened_limit_swaps: List[NativeThorTx]
    closed_limit_swaps: List[ClosedLimitSwap]
    partial_swaps: List[ThorEvent]

    def __bool__(self):
        return bool(self.new_opened_limit_swaps or self.closed_limit_swaps or self.partial_swaps)


class LimitSwapDetector(WithLogger, INotified, WithDelegates):
    REASON_EXPIRED = "limit swap expired"
    REASON_COMPLETED = "swap has been completed."
    REASON_CANCELLED = "limit swap cancelled"
    REASON_MARKET = "market swap completed"
    REASON_FAILED = "limit swap failed"

    @staticmethod
    def is_completed(status):
        return "completed" in status.lower()

    @staticmethod
    def get_closed_limit_swaps(block: BlockResult):
        all_types = set()

        for e in block.end_block_events:
            all_types.add(e.type)
            if e.type == 'limit_swap_close':
                yield e
            elif 'limit' in e.type:
                yield e
        for tx in block.txs:
            for e in tx.events:
                all_types.add(e.type)
                if 'limit' in e.type:
                    yield e
        print(f'All event types in block {block.block_no}: {all_types}')

    @staticmethod
    def get_swap_limit_end_block_events(block: BlockResult):
        """
        Yield end-block events where type == 'swap' and the memo indicates a limit swap.

        A limit-swap memo is recognized by the prefix '=<'. We read memo from event attrs
        using the same pattern used across the scanner (attrs.get('memo', '')).
        """
        for ev in block.end_block_events:
            try:
                if ev.type != 'swap':
                    continue

                # Prefer structured memo parsing when available
                pm = getattr(ev, 'parsed_memo', None)
                if pm is not None:
                    # THORMemo marks limit orders with ActionType.LIMIT_ORDER
                    if pm.action == ActionType.LIMIT_ORDER:
                        yield ev
                        continue

                # Fallback: raw memo string indicator (legacy support)
                memo = getattr(ev, 'memo', '')
                if isinstance(memo, str) and memo.startswith('=<'):
                    yield ev
            except Exception:
                # Defensive: skip malformed events but continue scanning
                continue

    @staticmethod
    def get_limit_swap_close_end_block_events(block: BlockResult):
        """
        Yield end-block events where type == 'limit_swap_close'.

        This is a narrow helper that only looks at end_block_events (not tx.logs)
        and yields events whose `type` equals 'limit_swap_close'.
        """
        for ev in block.end_block_events:
            try:
                if ev.type == 'limit_swap_close':
                    yield ev
            except Exception:
                continue

    @classmethod
    def get_limit_swap_close_reason(cls, ev: ThorEvent) -> str:
        """
        Extract and normalize closure reason from a `limit_swap_close` event.
        """
        attrs = ev.attrs if isinstance(ev.attrs, dict) else {}
        raw_reason = str(attrs.get('reason', '')).strip()

        raw_reason_l = raw_reason.lower()
        if 'expired' in raw_reason_l:
            return cls.REASON_EXPIRED
        if 'cancel' in raw_reason_l:
            return cls.REASON_CANCELLED
        if 'market' in raw_reason_l:
            return cls.REASON_MARKET
        if 'completed' in raw_reason_l:
            return cls.REASON_COMPLETED
        if 'failed' in raw_reason_l:
            return cls.REASON_FAILED

        return raw_reason

    @staticmethod
    def get_limit_swap_txs(block: BlockResult):
        """
        Yield block txs whose top-level memo parses as a limit-swap action.

        This covers both limit swap creation (`=<`) and modification (`m=<`).
        Only `block.txs` are scanned here; end-block events are handled by the
        dedicated helpers above.
        """
        for tx in block.txs:
            try:
                parsed = THORMemo.parse_memo(tx.memo or '', no_raise=True)
                if parsed and parsed.action in (ActionType.LIMIT_ORDER, ActionType.LIMIT_ORDER_MODIFY):
                    yield tx
            except Exception:
                continue

    @staticmethod
    def get_new_opened_limit_swap_txs(block: BlockResult):
        """
        Yield txs that open a new limit swap (`=<...`).

        This intentionally excludes modify memos (`m=<...`), because those are not
        newly opened orders.
        """
        for tx in block.txs:
            try:
                parsed = THORMemo.parse_memo(tx.memo or '', no_raise=True)
                if parsed and parsed.action == ActionType.LIMIT_ORDER:
                    yield tx
            except Exception:
                continue

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    async def on_data(self, sender, b: BlockResult):
        update = LimitSwapBlockUpdate(
            block_no=b.block_no,
            timestamp=int(b.timestamp or 0),
            new_opened_limit_swaps=list(self.get_new_opened_limit_swap_txs(b)),
            closed_limit_swaps=[
                ClosedLimitSwap(ev, self.get_limit_swap_close_reason(ev))
                for ev in self.get_limit_swap_close_end_block_events(b)
            ],
            partial_swaps=list(self.get_swap_limit_end_block_events(b)),
        )

        if update:
            self.logger.info(f'Block {update.block_no}: Detected {len(update.new_opened_limit_swaps)} new opened limit swaps, '
                             f'{len(update.closed_limit_swaps)} closed limit swaps, '
                             f'{len(update.partial_swaps)} partial swaps.')
            await self.pass_data_to_listeners(update)
