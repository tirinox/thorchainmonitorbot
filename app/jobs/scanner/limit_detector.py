from typing import List, NamedTuple, Optional

from api.aionode.types import thor_to_float
from jobs.scanner.block_result import BlockResult
from jobs.scanner.tx import NativeThorTx, ThorEvent, ThorObservedTx, ThorMessageType
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
        return str(attrs.get('txid') or attrs.get('id') or attrs.get('in_tx_id') or '')


class OpenedLimitSwap(NamedTuple):
    tx_id: str
    memo: str
    source_asset: str
    source_amount: int
    source_amount_float: float
    source_decimals: int = 8
    trader: str = ''
    target_asset: str = ''
    thor_block_no: int = 0


class LimitSwapBlockUpdate(NamedTuple):
    block_no: int
    timestamp: int
    new_opened_limit_swaps: List[OpenedLimitSwap]
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
    def _extract_native_trader(tx: NativeThorTx) -> str:
        for message in tx.messages:
            if signer := message.get('signer', ''):
                return str(signer)
            if from_address := message.get('from_address', ''):
                return str(from_address)
        return str(tx.first_signer_address or '')

    @staticmethod
    def _extract_native_first_coin(tx: NativeThorTx) -> tuple[str, int]:
        for message in tx.messages:
            if message.type == ThorMessageType.MsgDeposit and message.coins:
                coin = message.coins[0]
                return str(coin.get('asset', '')), int(coin.get('amount', 0))

            if message.is_send:
                amounts = message.get('amount', [])
                if amounts:
                    coin = amounts[0]
                    return str(coin.get('asset') or coin.get('denom', '')), int(coin.get('amount', 0))

        return '', 0

    @classmethod
    def _make_opened_limit_swap_from_native_tx(cls, tx: NativeThorTx) -> Optional[OpenedLimitSwap]:
        memo_txt = tx.memo or tx.first_message_memo or ''
        parsed = THORMemo.parse_memo(memo_txt, no_raise=True)
        if not parsed or parsed.action != ActionType.LIMIT_ORDER:
            return None

        source_asset, source_amount = cls._extract_native_first_coin(tx)
        return OpenedLimitSwap(
            tx_id=str(tx.tx_hash or ''),
            memo=memo_txt,
            source_asset=source_asset,
            source_amount=int(source_amount or 0),
            source_amount_float=thor_to_float(source_amount or 0),
            source_decimals=8,
            trader=cls._extract_native_trader(tx),
            target_asset=str(parsed.asset or ''),
            thor_block_no=int(tx.height or 0),
        )

    @staticmethod
    def _make_opened_limit_swap_from_observed_tx(tx: ThorObservedTx, thor_block_no: int = 0) -> Optional[OpenedLimitSwap]:
        parsed = THORMemo.parse_memo(tx.memo or '', no_raise=True)
        if not parsed or parsed.action != ActionType.LIMIT_ORDER:
            return None

        coin = tx.coins[0] if tx.coins else None
        source_amount = int(coin.amount if coin else 0)
        return OpenedLimitSwap(
            tx_id=str(tx.tx_id or ''),
            memo=str(tx.memo or ''),
            source_asset=str(coin.asset if coin else ''),
            source_amount=source_amount,
            source_amount_float=thor_to_float(source_amount),
            source_decimals=int(coin.decimals if coin else 8),
            trader=str(tx.from_address or ''),
            target_asset=str(parsed.asset or ''),
            thor_block_no=int(thor_block_no or 0),
        )

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

    @classmethod
    def build_closed_limit_swaps(cls, block: BlockResult) -> list[ClosedLimitSwap]:
        return [
            ClosedLimitSwap(ev, cls.get_limit_swap_close_reason(ev))
            for ev in cls.get_limit_swap_close_end_block_events(block)
        ]

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
        Yield normalized limit-swap openings from both THOR native deposits and
        observed external inbound txs.

        This intentionally excludes modify memos (`m=<...`), because those are not
        newly opened orders.
        """
        seen_tx_ids = set()

        for tx in block.deposits:
            try:
                opened = LimitSwapDetector._make_opened_limit_swap_from_native_tx(tx)
                if opened and opened.tx_id and opened.tx_id not in seen_tx_ids:
                    seen_tx_ids.add(opened.tx_id)
                    yield opened
            except Exception:
                continue

        for tx in block.all_observed_txs:
            try:
                opened = LimitSwapDetector._make_opened_limit_swap_from_observed_tx(tx, block.block_no)
                if opened and opened.tx_id and opened.tx_id not in seen_tx_ids:
                    seen_tx_ids.add(opened.tx_id)
                    yield opened
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
            closed_limit_swaps=self.build_closed_limit_swaps(b),
            partial_swaps=list(self.get_swap_limit_end_block_events(b)),
        )

        if update:
            self.logger.info(f'Block {update.block_no}: Detected {len(update.new_opened_limit_swaps)} new opened limit swaps, '
                             f'{len(update.closed_limit_swaps)} closed limit swaps, '
                             f'{len(update.partial_swaps)} partial swaps.')
            await self.pass_data_to_listeners(update)
