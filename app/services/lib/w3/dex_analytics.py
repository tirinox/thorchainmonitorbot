import json
from typing import List, NamedTuple, Dict

from services.lib.date_utils import DAY
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.lib.w3.token_record import AmountToken
from services.models.time_series import TimeSeries
from services.models.tx import ThorTxExtended


class DexReportEntry(NamedTuple):
    name: str  # asset or aggregator name depending on context
    rune_volume: float
    count: int


class DexReport(NamedTuple):
    total: DexReportEntry
    by_outer_asset: Dict[str, DexReportEntry]
    by_aggregator: Dict[str, DexReportEntry]
    swap_ins: DexReportEntry
    swap_outs: DexReportEntry


class DexTxPoint(NamedTuple):
    hash: str
    rune_volume: float
    swap_in: AmountToken
    swap_out: AmountToken


class DexAnalyticsCollector(WithLogger, INotified):
    KEY_DEX_TIME_SERIES = 'DEX:Analytics'
    KEY_DEX_COUNTED_TX_SET = 'DEX:CountedHashes'
    MAX_POINTS = 100_000

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.series = TimeSeries(self.KEY_DEX_TIME_SERIES, deps.db)

    async def is_counted(self, tx_hash) -> bool:
        if tx_hash:
            return await self.deps.db.redis.sismember(self.KEY_DEX_COUNTED_TX_SET, tx_hash)
        return True

    async def _mark_as_counted(self, tx_hash):
        if tx_hash:
            await self.deps.db.redis.sadd(self.KEY_DEX_COUNTED_TX_SET, tx_hash)

    async def on_data(self, sender, extended_txs: List[ThorTxExtended]):
        for tx in extended_txs:
            if tx.dex_aggregator_used and tx.full_rune > 0:
                tx_hash = tx.tx_hash
                if not (await self.is_counted(tx_hash)):
                    swap_in, swap_out = 'null', 'null'
                    if tx.dex_info.swap_in:
                        swap_in = json.dumps(tx.dex_info.swap_in.as_json)
                    if tx.dex_info.swap_out:
                        swap_out = json.dumps(tx.dex_info.swap_out.as_json)

                    await self.series.add(
                        hash=tx.tx_hash,
                        swap_in=swap_in,
                        swap_out=swap_out,
                        volume=tx.full_rune,
                    )
                    await self._mark_as_counted(tx_hash)

        await self.series.trim_oldest(self.MAX_POINTS)

    @staticmethod
    def make_dex_report_entry(points: List[DexTxPoint], name=None):
        return DexReportEntry(
            name, sum(p.rune_volume for p in points), len(points)
        )

    async def get_analytics(self, period=DAY) -> DexReport:
        def cvt_point(point) -> DexTxPoint:
            d = point[1]  # discard timestamps
            swap_in = AmountToken.from_json(d.get('swap_in'))
            swap_out = AmountToken.from_json(d.get('swap_out'))
            try:
                volume = float(d['volume'])
            except ValueError:
                volume = 0.0
            return DexTxPoint(d.get('hash'), volume, swap_in, swap_out)

        all_points = await self.series.get_last_points(period, max_points=self.MAX_POINTS)
        all_points = [cvt_point(p) for p in all_points]

        swap_in_report = self.make_dex_report_entry([p for p in all_points if p.swap_in])
        swap_out_report = self.make_dex_report_entry([p for p in all_points if p.swap_out])

        outer_assets = set([p.swap_in.token.symbol for p in all_points if p.swap_in] +
                           [p.swap_out.token.symbol for p in all_points if p.swap_out])

        by_outer_asset = {}
        for outer_asset in outer_assets:
            by_outer_asset[outer_asset] = self.make_dex_report_entry(
                [p for p in all_points if (
                        (p.swap_in and p.swap_in.token.symbol == outer_asset) or
                        (p.swap_out and p.swap_out.token.symbol == outer_asset)
                )],
                name=outer_asset
            )

        by_aggregator = {}
        aggregators = set([p.swap_in.aggr_name for p in all_points if p.swap_in] +
                          [p.swap_out.aggr_name for p in all_points if p.swap_out])
        for aggr_name in aggregators:
            by_aggregator[aggr_name] = self.make_dex_report_entry(
                [p for p in all_points if (
                        (p.swap_in and p.swap_in.aggr_name == aggr_name) or
                        (p.swap_out and p.swap_out.aggr_name == aggr_name)
                )],
                name=aggr_name
            )

        return DexReport(
            total=self.make_dex_report_entry(all_points),
            by_outer_asset=by_outer_asset,
            by_aggregator=by_aggregator,
            swap_ins=swap_in_report,
            swap_outs=swap_out_report,
        )
