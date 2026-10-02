"""
Offline replay of real THORChain transactions through the bot's own block scanner detectors and notifiers.

A case is one transaction kept in tx_corpus/<name>.json.gz:
  blocks    the blocks of its life, each trimmed to the txs and events that mention it
  pools     THORNode pools at the heights where the detectors priced it
  tape      every other THORNode answer the detectors asked for while it was recorded
  truth     Midgard's action and THORNode's tx details and status: the ground truth
  expected  what the bot must build (taken from the truth) and whether it must post (reviewed by a human)

tools/tx_corpus.py records a case by running this same harness online: then the tape fetches every answer
it does not have from THORNode and keeps it, and the pool cache fetches its snapshots.
"""
import gzip
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict

import yaml

from api.aionode.connector import ThorConnector
from api.aionode.env import ThorEnvironment
from api.aionode.types import ThorPool
from jobs.fetch.stream_watchlist import StreamingSwapStartDetectorFromList
from jobs.ref_memo_cache import RefMemoCache
from jobs.scanner.block_result import BlockResult
from jobs.scanner.swap_extractor import SwapExtractorBlock
from jobs.scanner.swap_start_detector import SwapStartDetectorFromBlock
from jobs.volume_filler import VolumeFillerUpdater
from lib.config import Config
from lib.constants import THOR_BLOCK_TIME
from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.money import DepthCurve
from models.memo import THORMemo
from models.pool_info import parse_thor_pools
from models.price import PriceHolder
from models.s_swap import AlertSwapStart, StreamingSwap
from models.tx import ThorAction, EventLargeTransaction
from notify.public.s_swap_notify import StreamingSwapStartTxNotifier
from notify.public.tx_notify import SwapTxNotifier
from tests.fakes import FakeDB, FakeRedis

CORPUS_DIR = Path(__file__).with_name('tx_corpus')
CONFIG_PATH = CORPUS_DIR / 'thresholds.yaml'
CASE_SUFFIX = '.json.gz'


# ------------------------------------------------------------------ cases on disk

def case_paths() -> List[Path]:
    return sorted(CORPUS_DIR.glob(f'*{CASE_SUFFIX}'))


def case_name(path: Path) -> str:
    return path.name[:-len(CASE_SUFFIX)]


def load_case(path: Path) -> dict:
    return json.loads(gzip.decompress(path.read_bytes()))


def save_case(case: dict, path: Path):
    data = json.dumps(case, sort_keys=True, separators=(',', ':')).encode()
    path.write_bytes(gzip.compress(data, mtime=0))  # mtime=0: the same case gives the same bytes


def load_frozen_config() -> Config:
    return Config(data=yaml.safe_load(CONFIG_PATH.read_text()))


def trim_block(raw: dict, height: int, tx_id: str) -> Optional[dict]:
    """Only the txs and events of the block that mention tx_id; None when there are none."""
    needle = tx_id.upper()

    def mentions(item):
        return needle in json.dumps(item).upper()

    txs = [tx for tx in raw.get('txs') or [] if mentions(tx)]
    begin = [ev for ev in raw.get('begin_block_events') or [] if mentions(ev)]
    end = [ev for ev in raw.get('end_block_events') or [] if mentions(ev)]
    if not (txs or begin or end):
        return None
    return {
        'height': height,
        'header': {'time': raw['header']['time']},
        'txs': txs,
        'begin_block_events': begin,
        'end_block_events': end,
    }


# ------------------------------------------------------------------ replayed data sources

class Tape:
    """
    THORNode answers by request. Recording, it fetches what it does not have and keeps it;
    replaying, a request it does not have is a miss: the detectors asked something new and the case must be re-recorded.
    """

    def __init__(self, records: Optional[dict] = None, fetch_missing=False):
        self.records = dict(records or {})
        self.fetch_missing = fetch_missing
        self.misses = []

    @staticmethod
    def key(*parts) -> str:
        return json.dumps(parts)

    async def answer(self, key, fetch):
        if key in self.records:
            return self.records[key]
        if self.fetch_missing:
            data = await fetch()
            self.records[key] = data
            return data
        self.misses.append(key)
        return None

    def attach(self, connector: ThorConnector) -> ThorConnector:
        live_request = connector._request

        async def _request(path, is_rpc=False, treat_empty_as_ok=True, paginated=False, height=None, collect_key=''):
            key = self.key('thor', path, is_rpc, paginated, height, collect_key)
            return await self.answer(
                key, lambda: live_request(path, is_rpc, treat_empty_as_ok, paginated, height, collect_key))

        connector._request = _request
        return connector


class ReplayPoolCache:
    """The pools of the latest snapshot at or before the block being replayed: what the bot's pool cache held then."""

    def __init__(self, snapshots: dict, stable_coins, fetch=None):
        self.snapshots = {int(h): pools for h, pools in snapshots.items()}
        self.stable_coins = stable_coins
        self.fetch = fetch  # async (height) -> raw THORNode pools, when recording
        self.height = 0
        self._holders = {}

    async def take_snapshot(self, height: int):
        # whole: the USD prices come from fields like asset_tor_price, so dropping fields breaks prices quietly
        self.snapshots[height] = await self.fetch(height)

    def snapshot_height(self, height: int) -> int:
        heights = sorted(self.snapshots)
        if not heights:
            raise LookupError('The case has no pool snapshots')
        before = [h for h in heights if h <= height]
        return before[-1] if before else heights[0]

    async def load_as_price_holder(self, height=None, caching=True) -> PriceHolder:
        h = self.snapshot_height(height or self.height)
        if h not in self._holders:
            ph = PriceHolder(self.stable_coins)
            ph.update_pools(parse_thor_pools([ThorPool.from_json(p) for p in self.snapshots[h]]))
            self._holders[h] = ph
        return self._holders[h]

    async def get(self) -> PriceHolder:
        return await self.load_as_price_holder()


class ReplayLastBlockCache:
    def __init__(self, timestamps: Dict[int, float]):
        self.timestamps = timestamps
        self.height = 0

    async def get_thor_block(self):
        return self.height

    async def get_timestamp_of_block(self, height):
        height = int(height)
        if height in self.timestamps:
            return self.timestamps[height]
        nearest = min(self.timestamps, key=lambda h: abs(h - height))
        return self.timestamps[nearest] + (height - nearest) * THOR_BLOCK_TIME


class Sink(INotified):
    def __init__(self):
        self.items = []

    async def on_data(self, sender, data):
        if isinstance(data, list):
            self.items.extend(data)
        else:
            self.items.append(data)


async def _as_is(event):
    return event


class ReplayStreamingWatchlist:
    """
    StreamingSwapWatchListFetcher polls THORNode's list of the ongoing streaming swaps, and every swap the chain splits
    into several sub-swaps is there, whatever its memo asked for. It is not recorded, so it is replayed from the
    blocks: a swap gets on the list at its first sub-swap event with a streaming_swap_quantity above 1, with the chain's
    quantity, as THORNode would list it. A rapid swap the chain splits and finishes between two polls is missed by the
    real watchlist, but not here.
    """

    def __init__(self, deps: DepContainer):
        self.detector = StreamingSwapStartDetectorFromList(deps)
        self.listed = set()

    def new_swaps(self, block: BlockResult) -> List[StreamingSwap]:
        found = []
        for ev in block.end_block_events:
            if ev.type != 'swap':
                continue
            tx_id = (ev.attrs.get('id') or '').upper()
            quantity = int(ev.attrs.get('streaming_swap_quantity') or 0)
            if quantity <= 1 or not tx_id or tx_id in self.listed:
                continue
            self.listed.add(tx_id)
            memo = THORMemo.parse_memo(ev.attrs.get('memo', ''), no_raise=True)
            found.append(StreamingSwap(
                tx_id=tx_id, quantity=quantity, count=int(ev.attrs.get('streaming_swap_count') or 1),
                interval=memo.s_swap_interval if memo else 0, last_height=block.block_no,
                source_asset=ev.attrs.get('_asset', ''), target_asset=memo.asset if memo else '',
            ))
        return found

    async def feed(self, block: BlockResult, ph: PriceHolder):
        for swap in self.new_swaps(block):
            await self.detector._handle_swap_start(swap, ph)


# ------------------------------------------------------------------ the pipeline

@dataclass
class ReplayResult:
    actions: List[ThorAction] = field(default_factory=list)  # swaps SwapExtractorBlock gave away
    given_away_at: Dict[str, int] = field(default_factory=dict)  # tx_id -> height
    starts: List[AlertSwapStart] = field(default_factory=list)  # swap starts the alert detector found
    watchlist_starts: List[AlertSwapStart] = field(default_factory=list)  # starts from the streaming swap list
    start_alerts: List[AlertSwapStart] = field(default_factory=list)  # starts the notifier let through
    swap_alerts: List[EventLargeTransaction] = field(default_factory=list)  # finished swaps it let through
    tape_misses: List[str] = field(default_factory=list)
    explained: Dict[str, dict] = field(default_factory=dict)  # tx_id -> SwapPipeline.explain


class SwapPipeline:
    """
    The block scanner subscribers of the swap alerts, wired as in main.py:
    RefMemoCache, SwapExtractorBlock -> VolumeFillerUpdater -> SwapTxNotifier,
    SwapStartDetectorFromBlock and the streaming swap watchlist (ReplayStreamingWatchlist) -> StreamingSwapStartTxNotifier.
    The DEX aggregator stage is left out (it asks EVM nodes), and so is the enrichment the notifiers do after
    the decision (Midgard fees, quotes, clout): neither changes what is posted.
    """

    def __init__(self, cfg: Config, thor_connector: ThorConnector, pool_cache: ReplayPoolCache,
                 last_block_cache: ReplayLastBlockCache):
        d = self.deps = DepContainer()
        d.cfg = cfg
        d.db = FakeDB(FakeRedis())
        d.thor_connector = thor_connector
        d.pool_cache = pool_cache
        d.last_block_cache = last_block_cache
        d.ref_memo_cache = RefMemoCache(d)

        self.extractor = SwapExtractorBlock(d)
        self.actions = Sink()
        self.extractor.add_subscriber(self.actions)

        volume_filler = VolumeFillerUpdater(d)
        self.extractor.add_subscriber(volume_filler)

        curve = DepthCurve(cfg.get_pure('tx.curve', default=DepthCurve.DEFAULT_TX_VS_DEPTH_CURVE))
        self.swap_notifier = SwapTxNotifier(d, cfg.tx.swap, curve=curve)
        self.swap_notifier._event_transform = _as_is
        volume_filler.add_subscriber(self.swap_notifier)
        self.swap_alerts = Sink()
        self.swap_notifier.add_subscriber(self.swap_alerts)

        self.start_detector = SwapStartDetectorFromBlock(
            d, dedup_component=SwapStartDetectorFromBlock.ALERT_DEDUP_COMPONENT)
        self.stream_notifier = StreamingSwapStartTxNotifier(d)
        self.stream_notifier.load_extra_tx_information = _as_is
        self.start_alerts = Sink()
        self.stream_notifier.add_subscriber(self.start_alerts)

        self.watchlist = ReplayStreamingWatchlist(d)
        self.watchlist_starts = Sink()
        self.watchlist.detector.add_subscriber(self.watchlist_starts)
        self.watchlist.detector.add_subscriber(self.stream_notifier)

        self.result = ReplayResult()

    async def feed(self, block: BlockResult):
        h = block.block_no
        self.deps.pool_cache.height = h
        self.deps.last_block_cache.height = h

        await self.deps.ref_memo_cache.on_data(None, block)

        n_before = len(self.actions.items)
        await self.extractor.on_data(None, block)
        for action in self.actions.items[n_before:]:
            self.result.given_away_at[action.tx_hash] = h

        # SwapStartDetectorFromBlock.on_data only defers the same call by a block, to be sure the tx is in the chain
        ph = await self.deps.pool_cache.get()
        starts = await self.start_detector.detect_swaps(block, ph)
        self.result.starts.extend(starts)
        for start in starts:
            await self.stream_notifier.on_data(None, start)

        await self.watchlist.feed(block, ph)

    async def explain(self, tx: ThorAction, height: int) -> dict:
        """The numbers SwapTxNotifier decides by, in USD, for a human to review its decision."""
        n = self.swap_notifier
        ph = await self.deps.pool_cache.load_as_price_holder(height)
        usd = ph.usd_per_rune
        depth = n._get_min_usd_depth(tx, ph)
        curve_min = depth * n.curve.evaluate(depth) * n.curve_mult if depth and n.curve else 0.0
        return {
            'volume_usd': tx.full_volume_in_rune * usd,
            'min_usd': max(n.min_usd_total, curve_min),
            'pool_depth_usd': depth,
            'streaming': tx.is_streaming, 'streaming_min_usd': n.min_streaming_swap_usd,
            'trade_asset': tx.is_trade_asset_involved, 'trade_min_usd': n.min_trade_asset_swap_usd,
            'affiliate_fee_usd': tx.meta_swap.affiliate_fee * tx.full_volume_in_rune * usd,
            'affiliate_min_usd': n.aff_fee_min_usd,
        }

    def finish(self, tape: Tape) -> ReplayResult:
        r = self.result
        r.actions = list(self.actions.items)
        r.watchlist_starts = list(self.watchlist_starts.items)
        r.start_alerts = list(self.start_alerts.items)
        r.swap_alerts = list(self.swap_alerts.items)
        r.tape_misses = list(tape.misses)
        return r


def case_blocks(case: dict) -> List[BlockResult]:
    blocks = [BlockResult.load_block(raw, raw['height']) for raw in case['blocks']]
    return [b.only_successful for b in sorted(blocks, key=lambda b: b.block_no)]


async def replay_case(case: dict, cfg: Optional[Config] = None,
                      live_thor: Optional[ThorConnector] = None, fetch_pools=None) -> ReplayResult:
    """
    Offline by default. With live_thor (and fetch_pools) it records instead: the THORNode answers it gets are
    added to case['tape'] and the pool snapshots of case['pool_heights'] to case['pools'].
    """
    cfg = cfg or load_frozen_config()
    blocks = case_blocks(case)

    recording = live_thor is not None
    tape = Tape(case.get('tape'), fetch_missing=recording)
    thor = tape.attach(live_thor or ThorConnector(ThorEnvironment(), None))

    pool_cache = ReplayPoolCache(case.get('pools', {}), cfg.stable_coins, fetch=fetch_pools)
    if recording:
        for h in case['pool_heights']:
            if h not in pool_cache.snapshots:
                await pool_cache.take_snapshot(h)

    last_block_cache = ReplayLastBlockCache({b.block_no: b.timestamp for b in blocks})

    pipeline = SwapPipeline(cfg, thor, pool_cache, last_block_cache)
    for block in blocks:
        await pipeline.feed(block)
    result = pipeline.finish(tape)
    for action in result.actions:
        result.explained[action.tx_hash] = await pipeline.explain(action, result.given_away_at[action.tx_hash])

    if recording:
        case['tape'] = tape.records
        case['pools'] = {str(h): pools for h, pools in pool_cache.snapshots.items()}
    return result


# ------------------------------------------------------------------ what was built vs the truth

def _address(a: str) -> str:
    return (a or '').lower() if (a or '').lower().startswith('0x') else (a or '')


def _sum_by(rows) -> list:
    totals = defaultdict(int)
    for key, amount in rows:
        totals[key] += int(amount)
    return sorted([*key, amount] for key, amount in totals.items())


def _affiliate_fee_addresses(case: dict) -> set:
    return {
        _address(ev['rune_address'])
        for block in case['blocks'] for ev in block['end_block_events'] + block['begin_block_events']
        if ev.get('type') == 'affiliate_fee' and ev.get('rune_address')
    }


def expected_swap(case: dict) -> Optional[dict]:
    """
    What the bot must build from the truth of the case, or None when it must not give a swap away:
    no swap happened at all (a full refund, the bot does not announce those), or the case says why (no_swap_reason).
      in       all of Midgard's actions of the tx: a partial refund is a swap action and a refund action
      out      THORNode's out_txs: Midgard lists the output of a trade asset swap twice
      affiliate_out  the outputs to the addresses of the affiliate_fee events or of Midgard's affiliate outputs,
               but never to the swap's destination or sender: Midgard marks the user's own output as an affiliate's
               when the affiliates are paid in the same asset
    Whether it is streaming is not compared: the bot decides by the Advanced Swap Queue, Midgard by its own flag.
    """
    if case.get('no_swap_reason'):
        return None
    actions = case['truth']['midgard']
    swaps = [a for a in actions if a['type'] == 'swap']
    if not swaps:
        return None
    meta = swaps[0].get('metadata', {}).get('swap', {})
    ss = meta.get('streamingSwapMeta') or {}

    memo = THORMemo.parse_memo(meta.get('memo', ''), no_raise=True)
    own = {_address(tx['address']) for a in actions for tx in a.get('in', [])}
    if memo and memo.dest_address:
        own.add(_address(memo.dest_address))
    affiliates = _affiliate_fee_addresses(case)
    affiliates |= {_address(tx['address']) for a in actions for tx in a.get('out', []) if tx.get('affiliate')}
    affiliates -= own

    status = case['truth'].get('thornode_status')
    if status and status.get('out_txs') is not None:
        outs = [(_address(tx['to_address']), c) for tx in status['out_txs'] for c in tx['coins']]
    else:
        outs = [(_address(tx['address']), c) for tx in swaps[0].get('out', []) for c in tx['coins']]
    return {
        'in': _sum_by(((c['asset'],), c['amount']) for a in actions for tx in a.get('in', []) for c in tx['coins']),
        'out': _sum_by(((a, c['asset']), c['amount']) for a, c in outs if a not in affiliates),
        'affiliate_out': _sum_by(((a, c['asset']), c['amount']) for a, c in outs if a in affiliates),
        # Midgard has no streaming block for a single swap: None is not compared.
        # Its count is of all the sub-swaps tried, the bot's of the successful ones
        'streaming_quantity': int(ss['quantity']) if ss.get('quantity') else None,
        'streaming_count': int(ss['count']) - len(ss.get('failedSwaps') or []) if ss.get('count') else None,
        'liquidity_fee': sum(int(a['metadata']['swap'].get('liquidityFee', 0) or 0) for a in swaps),
        'pools': sorted({p for a in swaps for p in a.get('pools', [])}),
    }


def summarize_swap(tx: ThorAction) -> dict:
    ss = tx.meta_swap.streaming if tx.meta_swap else None
    return {
        'in': _sum_by(((c.asset,), c.amount) for sub in tx.in_tx for c in sub.coins),
        'out': _sum_by(((_address(sub.address), c.asset), c.amount)
                       for sub in tx.out_tx if not sub.is_affiliate for c in sub.coins),
        'affiliate_out': _sum_by(((_address(sub.address), c.asset), c.amount)
                                 for sub in tx.out_tx if sub.is_affiliate for c in sub.coins),
        'is_streaming': bool(tx.is_streaming),
        'streaming_quantity': int(ss.quantity) if ss else 0,
        'streaming_count': int(ss.count) if ss else 0,
        'liquidity_fee': int(tx.meta_swap.liquidity_fee) if tx.meta_swap else 0,
        'pools': sorted(tx.pools),
    }


def alerts_of(result: ReplayResult, tx_id: str) -> dict:
    return {
        'stream_start': any(a.tx_id == tx_id for a in result.start_alerts),
        'swap_finished': any(e.transaction.tx_hash == tx_id for e in result.swap_alerts),
    }


def diff_swap(expected: Optional[dict], actual: Optional[dict], known_issues: dict) -> List[str]:
    """Mismatches as text; a field listed in known_issues is reported only when it does not differ any more."""
    if expected is None:
        return [] if actual is None else ['no swap happened, but the bot gave one away']
    if actual is None:
        return ['the swap was never given away']
    problems = []
    for key, want in expected.items():
        if want is None:
            continue
        got = actual.get(key)
        if key in known_issues:
            if got == want:
                problems.append(f'{key}: matches now, remove it from known_issues ({known_issues[key]})')
            continue
        if got != want:
            problems.append(f'{key}: bot {got!r} != truth {want!r}')
    return problems
