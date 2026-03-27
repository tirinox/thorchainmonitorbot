from datetime import datetime
from typing import List, Optional

from lib.accumulator import DailyAccumulator
from lib.constants import SYNTH_MODULE
from lib.date_utils import DAY, now_ts
from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.transfer import NativeTokenTransfer


class RuneTransferRecorder(INotified, WithLogger):
    """
    Accumulates daily Rune transfer statistics using DailyAccumulator.

    Metrics stored per day:
      - volume_rune        : total RUNE volume of all qualifying transfers
      - transfer_count     : number of qualifying transfers
      - cex_inflow_rune    : RUNE sent *to* a CEX address (deposits into CEX)
      - cex_outflow_rune   : RUNE sent *from* a CEX address (withdrawals from CEX)
      - cex_inflow_count   : number of CEX deposit transfers
      - cex_outflow_count  : number of CEX withdrawal transfers
    """

    ACCUM_NAME = 'RuneTransfers'

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

        cfg = deps.cfg.get('token_transfer')
        self.cex_list = set(cfg.as_list('cex_list'))
        self.ignore_cex2cex = bool(cfg.get('ignore_cex2cex', True))

        self.accumulator = DailyAccumulator(self.ACCUM_NAME, deps.db)

    # ── filtering ─────────────────────────────────────────────────────────

    def _is_cex(self, addr: str) -> bool:
        return bool(addr) and addr in self.cex_list

    def _is_cex2cex(self, transfer: NativeTokenTransfer) -> bool:
        return self._is_cex(transfer.from_addr) and self._is_cex(transfer.to_addr)

    def _should_skip(self, transfer: NativeTokenTransfer) -> bool:
        """Return True if the transfer should be excluded from statistics."""
        if not transfer.is_rune:
            return True

        if transfer.is_comment_non_send():
            self.logger.debug(f'Skipping non-send comment: {transfer.comment!r} in {transfer}')
            return True

        # Ignore deposits to internal SYNTH_MODULE (e.g. TCY stakes)
        if transfer.to_addr == SYNTH_MODULE:
            self.logger.debug(f'Skipping SYNTH_MODULE deposit: {transfer}')
            return True

        if self.ignore_cex2cex and self._is_cex2cex(transfer):
            self.logger.debug(f'Skipping CEX-to-CEX transfer: {transfer}')
            return True

        return False

    # ── recording ─────────────────────────────────────────────────────────

    async def _record_transfer(self, transfer: NativeTokenTransfer, ts: float):
        amount = transfer.amount
        fields = {
            'volume_rune': amount,
            'transfer_count': 1,
        }

        if self._is_cex(transfer.to_addr):
            fields['cex_inflow_rune'] = amount
            fields['cex_inflow_count'] = 1

        if self._is_cex(transfer.from_addr):
            fields['cex_outflow_rune'] = amount
            fields['cex_outflow_count'] = 1

        await self.accumulator.add(ts, **fields)

    # ── INotified ─────────────────────────────────────────────────────────

    async def on_data(self, sender, transfers: List[NativeTokenTransfer]):
        for transfer in transfers:
            if not self._should_skip(transfer):
                ts = transfer.block_ts if transfer.block_ts else now_ts()
                await self._record_transfer(transfer, ts)

    # ── read-back helpers ─────────────────────────────────────────────────

    @staticmethod
    def _empty_snapshot() -> dict:
        return {
            'volume_rune': 0.0,
            'transfer_count': 0.0,
            'cex_inflow_rune': 0.0,
            'cex_outflow_rune': 0.0,
            'cex_inflow_count': 0.0,
            'cex_outflow_count': 0.0,
        }

    @staticmethod
    def _date_str(ts: float) -> str:
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d')

    @classmethod
    def _normalize_snapshot(cls, ts: float, raw: Optional[dict]) -> dict:
        snap = cls._empty_snapshot()
        if raw:
            for key in snap:
                if key in raw:
                    snap[key] = float(raw[key])
        return {
            'date': cls._date_str(ts),
            'timestamp': int(ts),
            **snap,
            'cex_netflow_rune': snap['cex_inflow_rune'] - snap['cex_outflow_rune'],
        }

    async def get_daily_data(self, days: int = 14, end_ts: Optional[float] = None) -> List[dict]:
        """
        Return a list of daily snapshot dicts, oldest first, covering *days* days.
        Each dict has keys: date, timestamp, volume_rune, transfer_count,
        cex_inflow_rune, cex_outflow_rune, cex_inflow_count, cex_outflow_count,
        cex_netflow_rune.
        """
        if days <= 0:
            raise ValueError('days must be > 0')

        end_ts = float(end_ts or now_ts())
        items = []
        for offset in range(days - 1, -1, -1):
            ts = end_ts - offset * DAY
            raw = await self.accumulator.get(ts)
            items.append(self._normalize_snapshot(ts, raw))
        return items

    async def get_summary(self, days: int = 14, end_ts: Optional[float] = None) -> dict:
        """
        Return an aggregated summary over *days* days (totals + daily breakdown).
        """
        daily = await self.get_daily_data(days=days, end_ts=end_ts)

        totals = self._empty_snapshot()
        for day in daily:
            for key in totals:
                totals[key] += day.get(key, 0.0)

        return {
            'days': days,
            'start_date': daily[0]['date'] if daily else '',
            'end_date': daily[-1]['date'] if daily else '',
            **totals,
            'cex_netflow_rune': totals['cex_inflow_rune'] - totals['cex_outflow_rune'],
            'daily': daily,
        }

