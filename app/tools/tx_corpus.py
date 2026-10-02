"""
The regression corpus of real THORChain transactions (tests/regression/tx_corpus).

  find      page through Midgard's swaps, sort them into categories, show examples of the ones not covered yet
  add       record a tx as a case: its trimmed blocks, the pools, THORNode's answers and Midgard's truth
  rerecord  take the pools and THORNode's answers of cases again (the blocks are kept)
  report    replay every case offline and compare what the bot built and posted with the truth
  approve   accept the bot's alert decisions of a case after a review

Run from app/, e.g.: PYTHONPATH=. python tools/tx_corpus.py add 26D5E260...
Blocks and historic state come from our THORNode while it still has them (thor.node.node_url),
older ones from the archive (thor.node.backup_node_url). Midgard (thor.midgard.public_url) has all the history.
"""
import argparse
import asyncio
import datetime
import json
import logging
import re
import sys
from collections import defaultdict
from typing import Optional

import aiohttp

from api.aionode.connector import ThorConnector
from api.midgard.connector import MidgardConnector
from lib.config import Config
from lib.utils import safe_get
from models.asset import Asset, is_rune
from models.memo import THORMemo, ActionType
from tests.regression.harness import (
    CORPUS_DIR, CASE_SUFFIX, case_paths, case_name, load_case, save_case, trim_block, replay_case,
    expected_swap, summarize_swap, alerts_of, diff_swap,
)

DOWNLOAD_PARALLEL = 16
DEFAULT_BLOCKS_BACK = 30  # the inbound is often observed a few blocks before its consensus
DEFAULT_BLOCKS_AFTER = 3
DEFAULT_MAX_WINDOW = 1500


# ------------------------------------------------------------------ data sources

def _is_error(data) -> bool:
    return isinstance(data, dict) and bool(data.get('code')) and 'message' in data


class Sources:
    def __init__(self, cfg: Config, session: aiohttp.ClientSession):
        env = cfg.get_thor_env_by_network_id()
        self.node = ThorConnector(env, session)
        self.archive = ThorConnector(cfg.get_thor_env_by_network_id(backup=True), session)
        self.midgard = MidgardConnector(session, 3, public_url=env.midgard_url)
        self.earliest = 0  # the first block our THORNode still has

    async def init(self):
        status = await self.node.query_native_status_raw()
        self.earliest = int(safe_get(status, 'result', 'sync_info', 'earliest_block_height') or 0)
        logging.info(f'Our THORNode has blocks from #{self.earliest}')

    def has(self, height) -> bool:
        return bool(height) and int(height) >= self.earliest

    async def thor(self, path, is_rpc=False, treat_empty_as_ok=True, paginated=False, height=None, collect_key=''):
        """Our THORNode, or the archive for a height it no longer has or when it fails."""
        if height is None and (m := re.search(r'[?&]height=(\d+)', path)):
            asked_height = int(m.group(1))
        else:
            asked_height = height
        args = (path, is_rpc, treat_empty_as_ok, paginated, height, collect_key)
        if asked_height is None or self.has(asked_height):
            data = await self.node._request(*args)
            if data and not _is_error(data):
                return data
        data = await self.archive._request(*args)
        return None if _is_error(data) else data

    def recording_connector(self) -> ThorConnector:
        connector = ThorConnector(self.node.env, self.node.session)
        connector._request = self.thor
        return connector

    async def block(self, height):
        return await self.thor(self.node.env.path_thorchain_block_by_height, height=height)

    async def pools(self, height):
        return await self.thor(self.node.env.path_pools_height, treat_empty_as_ok=False, height=height)

    async def actions(self, tx_id) -> list:
        """All of Midgard's actions of the tx: a partial refund is a swap action and a refund action."""
        return (await self.midgard.request(f'v2/actions?txid={tx_id}')).get('actions') or []

    async def truth(self, tx_id) -> dict:
        return {
            'midgard': await self.actions(tx_id),
            'thornode_details': await self.thor(self.node.env.path_tx_details.format(txid=tx_id)),
            'thornode_status': await self.thor(self.node.env.path_tx_status.format(txid=tx_id)),
        }


def main_action(actions: list) -> Optional[dict]:
    return next((a for a in actions if a['type'] == 'swap'), actions[0] if actions else None)


# ------------------------------------------------------------------ categories

def asset_kind(asset: str) -> str:
    if is_rune(asset):
        return 'rune'
    a = Asset.from_string(asset)
    if a.is_trade:
        return 'trade'
    if a.is_secured:
        return 'secured'
    if a.is_synth:
        return 'synth'
    if a.chain == 'THOR':
        return 'thor_token'
    return 'l1'


def describe_action(action: dict) -> Optional[dict]:
    """Midgard's swap or refund as the tags of its category, or None when it is not a finished swap."""
    meta = action.get('metadata', {}).get('swap') or action.get('metadata', {}).get('refund') or {}
    in_coins = [c for tx in action.get('in', []) for c in tx.get('coins', [])]
    if not in_coins or action.get('status') == 'pending':
        return None
    in_asset = in_coins[0]['asset']

    memo_str = meta.get('memo', '')
    memo = THORMemo.parse_memo(memo_str, no_raise=True) if memo_str else None
    if memo and memo.action in (ActionType.LIMIT_ORDER, ActionType.LIMIT_ORDER_MODIFY):
        return None  # limit swaps go to a later batch

    user_outs = [(tx, c) for tx in action.get('out', []) if not tx.get('affiliate') for c in tx.get('coins', [])]
    aff_outs = [tx for tx in action.get('out', []) if tx.get('affiliate')]
    out_assets = [c['asset'] for _, c in user_outs if c['asset'] != in_asset]
    out_asset = out_assets[0] if out_assets else (memo.asset if memo and memo.asset else in_asset)

    ss = meta.get('streamingSwapMeta') or {}
    quantity, count = int(ss.get('quantity', 0) or 0), int(ss.get('count', 0) or 0)
    refund = action.get('type') == 'refund' or any(c['asset'] == in_asset for _, c in user_outs)

    height = int(action['height'])
    out_heights = [int(tx.get('height') or 0) for tx in action.get('out', [])]
    last_height = int(ss.get('lastHeight') or 0)
    finish = max([height, last_height, *out_heights])

    tags = [
        'swap',
        f'in:{asset_kind(in_asset)}', f'out:{asset_kind(out_asset)}',
        f'in_chain:{in_asset.split(".")[0].split("~")[0]}',
        'streaming' if meta.get('isStreamingSwap') else 'single',
        f'aff:{min(len({tx["address"] for tx in aff_outs}), 2)}',
    ]
    if refund:
        tags.append('refund')
    # several outbounds of the user, not counting Midgard's second copy of a trade asset output (txID = the inbound)
    in_tx_id = action['in'][0].get('txID', '')
    if len({tx['txID'] for tx, _ in user_outs if tx.get('txID') and tx['txID'] != in_tx_id}) > 1:
        tags.append('multi_leg')
    if memo and memo.dex_aggregator_address:
        tags.append('dex_out')
    if quantity and count < quantity:
        tags.append('partial')

    in_amount = int(in_coins[0]['amount']) / 1e8
    return {
        'tx_id': action['in'][0]['txID'],
        'height': height,
        'window': finish - height,
        'usd': in_amount * float(meta.get('inPriceUSD') or 0),
        'tags': tags,
        'signature': ' '.join(t for t in tags if not t.startswith('in_chain:')),
        'route': f'{in_asset} -> {out_asset}',
        'memo': memo_str,
    }


def short(tx_id: str) -> str:
    return tx_id[:8]


def links(tx_id: str) -> dict:
    return {
        'thorchain.net': f'https://thorchain.net/tx/{tx_id}',
        'runescan': f'https://runescan.io/tx/{tx_id}',
    }


# ------------------------------------------------------------------ commands

async def cmd_find(src: Sources, args):
    covered = defaultdict(list)
    for path in case_paths():
        case = load_case(path)
        covered[' '.join(t for t in case['tags'] if not t.startswith(('in_chain:', 'inbound:')))].append(case_name(path))

    min_height = max(src.earliest + DEFAULT_BLOCKS_BACK, args.min_height or 0)
    found = defaultdict(list)
    queries = [f'type={t}' for t in args.types.split(',')]
    queries += [f'type=swap&asset={a}' for a in args.assets.split(',') if a]
    for query in queries:
        token, scanned = '', 0
        for _ in range(args.pages):
            page = await src.midgard.request(
                f'v2/actions?{query}&limit=50' + (f'&nextPageToken={token}' if token else ''))
            actions = page.get('actions') or []
            for action in actions:
                scanned += 1
                if int(action['height']) < min_height:
                    continue
                if (d := describe_action(action)) and d['window'] <= args.max_window:
                    if all(x['tx_id'] != d['tx_id'] for x in found[d['signature']]):
                        found[d['signature']].append(d)
            token = (page.get('meta') or {}).get('nextPageToken')
            if not actions or not token or int(actions[-1]['height']) < min_height:
                break
        print(f'{query}: scanned {scanned} actions', file=sys.stderr)

    for signature in sorted(found, key=lambda s: -len(found[s])):
        items = sorted(found[signature], key=lambda d: -d['usd'])
        mark = f'covered by {", ".join(covered[signature])}' if signature in covered else 'NEW'
        print(f'\n[{len(items):4}] {signature}  ({mark})')
        # the biggest ones and the smallest, so both sides of the alert thresholds get examples
        picks = items[:args.examples] + [d for d in items[-1:] if d not in items[:args.examples]]
        for d in picks:
            print(f'       {d["tx_id"]}  #{d["height"]}  ${d["usd"]:>12,.0f}  window {d["window"]:>4}  '
                  f'{d["route"]}  {d["memo"][:50]}')


def inbound_message_type(case: dict) -> str:
    tx_id = case['tx_id'].upper()
    for block in case['blocks']:
        for tx in block['txs']:
            if (tx.get('hash') or '').upper() == tx_id:
                messages = safe_get(tx, 'tx', 'body', 'messages') or safe_get(tx, 'tx', 'messages') or []
                types = {m.get('@type', '').split('.')[-1] for m in messages}
                return 'inbound:' + ('+'.join(sorted(types)) or 'unknown')
    return 'inbound:observed'


async def download_window(src: Sources, tx_id: str, start: int, end: int) -> list:
    sem = asyncio.Semaphore(DOWNLOAD_PARALLEL)
    trimmed = {}

    async def one(h):
        async with sem:
            for attempt in range(3):
                raw = await src.block(h)
                if raw and 'header' in raw:
                    trimmed[h] = trim_block(raw, h, tx_id)
                    return
                await asyncio.sleep(1 + attempt)
            raise RuntimeError(f'Cannot get block #{h}')

    await asyncio.gather(*(one(h) for h in range(start, end + 1)))
    return [trimmed[h] for h in sorted(trimmed) if trimmed[h]]


async def cmd_add(src: Sources, args):
    tx_id = args.tx_id.upper()
    truth = await src.truth(tx_id)
    action = main_action(truth['midgard'])
    if not action:
        sys.exit(f'Midgard does not know {tx_id}')
    described = describe_action(action)
    if not described:
        sys.exit(f'{tx_id} is not a finished swap ({action.get("type")}, {action.get("status")})')
    if any(a['type'] == 'refund' for a in truth['midgard']) and 'refund' not in described['tags']:
        described['tags'].append('refund')

    consensus = int((truth['thornode_details'] or {}).get('consensus_height') or action['height'])
    heights = [int(a['height']) for a in truth['midgard']]
    heights += [int(tx.get('height') or 0) for a in truth['midgard'] for tx in a.get('out', [])]

    start = consensus - args.back
    end = action_finish = max(heights + [int(action['height']) + described['window']])
    end = max(end, consensus) + args.after
    if end - start > args.max_window:
        sys.exit(f'The window #{start}..#{end} is {end - start} blocks, more than --max-window {args.max_window}')

    print(f'{tx_id}: {described["route"]}, blocks #{start}..#{end}', file=sys.stderr)
    blocks = await download_window(src, tx_id, start, end)
    if not blocks:
        sys.exit('No block mentions the tx')

    name = args.name or f'{described["signature"].replace(" ", "_").replace(":", "-")}__{short(tx_id)}'
    case = {
        'version': 1,
        'tx_id': tx_id,
        'title': args.title or described['route'],
        'tags': described['tags'],
        'added': datetime.date.today().isoformat(),
        'links': links(tx_id),
        'notes': args.notes or '',
        'truth': truth,
        'blocks': blocks,
        'pool_heights': sorted({blocks[0]['height'], max(action_finish, blocks[0]['height'])}),
        'pools': {},
        'tape': {},
        'expected': {},
        'known_issues': {},
    }
    case['tags'].append(inbound_message_type(case))
    case['expected']['swap'] = expected_swap(case)

    result = await replay_case(case, live_thor=src.recording_connector(), fetch_pools=src.pools)
    case['expected']['alerts'] = alerts_of(result, tx_id)
    case['expected']['alerts_reviewed'] = False

    path = CORPUS_DIR / f'{name}{CASE_SUFFIX}'
    save_case(case, path)
    print(f'Saved {path.name}: {len(blocks)} blocks, {path.stat().st_size / 1024:.0f} KiB', file=sys.stderr)
    print_case_report(case_name(path), case, result)


def print_case_report(name: str, case: dict, result) -> bool:
    tx_id = case['tx_id']
    action = next((a for a in result.actions if a.tx_hash == tx_id), None)
    actual = summarize_swap(action) if action else None
    problems = diff_swap(case['expected']['swap'], actual, case.get('known_issues', {}))

    alerts = alerts_of(result, tx_id)
    want_alerts = case['expected'].get('alerts')
    if want_alerts is not None and alerts != want_alerts:
        problems.append(f'alerts: bot {alerts} != approved {want_alerts}')
    if result.tape_misses:
        problems.append(f'{len(result.tape_misses)} THORNode requests are not on the tape, re-record it')

    ok = not problems
    review = '' if case['expected'].get('alerts_reviewed') else '  [alerts not reviewed]'
    print(f'\n{"OK  " if ok else "FAIL"} {name}  {case["title"]}{review}')
    print(f'     {case["links"]["thorchain.net"]}')
    if action:
        midgard = main_action(case['truth']['midgard'])
        meta = midgard.get('metadata', {}).get('swap', {})
        in_usd = sum(int(c['amount']) for a in case['truth']['midgard'] for tx in a['in'] for c in tx['coins']
                     ) / 1e8 * float(meta.get('inPriceUSD') or 0)
        if bool(meta.get('isStreamingSwap')) != bool(action.is_streaming):
            print(f'     ~ streaming: bot {action.is_streaming}, Midgard {bool(meta.get("isStreamingSwap"))} '
                  f'(memo {meta.get("memo", "")[:60]})')
        e = result.explained.get(tx_id, {})
        rules = [f'volume ${e["volume_usd"]:,.0f} (Midgard ${in_usd:,.0f}) vs min ${e["min_usd"]:,.0f} '
                 f'(pool depth ${e["pool_depth_usd"]:,.0f})']
        if e['streaming']:
            rules.append(f'streaming: min ${e["streaming_min_usd"]:,.0f}')
        if e['trade_asset']:
            rules.append(f'trade asset: min ${e["trade_min_usd"]:,.0f}')
        if e['affiliate_fee_usd']:
            rules.append(f'affiliate fee ${e["affiliate_fee_usd"]:,.0f} vs ${e["affiliate_min_usd"]:,.0f}')
        print(f'     given away at #{result.given_away_at.get(tx_id)}; '
              f'stream start alert: {alerts["stream_start"]}, finish alert: {alerts["swap_finished"]}')
        print(f'     {"; ".join(rules)}')
    starts = [s for s in result.starts if s.tx_id == tx_id]
    if starts:
        s = starts[0]
        print(f'     start seen at #{s.block_height}: streaming={s.is_streaming}, volume ${s.volume_usd:,.0f}')
    else:
        print('     start never seen by the swap start detector')
    if listed := [s for s in result.watchlist_starts if s.tx_id == tx_id]:
        s = listed[0]
        print(f'     on the streaming swap list from #{s.block_height}: quantity {s.quantity}, volume ${s.volume_usd:,.0f}')
    for p in problems:
        print(f'     - {p}')
    for issue, reason in case.get('known_issues', {}).items():
        print(f'     ~ known issue {issue}: {reason}')
    return ok


async def cmd_rerecord(src: Sources, args):
    """Keeps the blocks and the truth, takes the pools and THORNode's answers again; the alerts are to be reviewed."""
    for path in case_paths():
        name = case_name(path)
        if args.names and name not in args.names:
            continue
        case = load_case(path)
        case['pools'], case['tape'] = {}, {}
        case['truth'] = await src.truth(case['tx_id'])
        case['expected']['swap'] = expected_swap(case)
        result = await replay_case(case, live_thor=src.recording_connector(), fetch_pools=src.pools)
        case['expected']['alerts'] = alerts_of(result, case['tx_id'])
        case['expected']['alerts_reviewed'] = False
        save_case(case, path)
        print_case_report(name, case, result)


async def cmd_report(_src, args):
    paths = [p for p in case_paths() if not args.names or case_name(p) in args.names]
    failed = 0
    for path in paths:
        case = load_case(path)
        result = await replay_case(case)
        failed += not print_case_report(case_name(path), case, result)
    print(f'\n{len(paths) - failed} of {len(paths)} cases match')


async def cmd_approve(_src, args):
    for name in args.names:
        path = CORPUS_DIR / f'{name}{CASE_SUFFIX}'
        case = load_case(path)
        result = await replay_case(case)
        case['expected']['alerts'] = alerts_of(result, case['tx_id'])
        case['expected']['alerts_reviewed'] = True
        save_case(case, path)
        print(f'{name}: alerts approved as {case["expected"]["alerts"]}')


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('find')
    p.add_argument('--types', default='swap,refund')
    p.add_argument('--assets', default='', help='also swaps of these assets, comma separated (Midgard\'s asset filter)')
    p.add_argument('--pages', type=int, default=40, help='pages of 50 actions per type')
    p.add_argument('--examples', type=int, default=2)
    p.add_argument('--min-height', type=int, default=0)
    p.add_argument('--max-window', type=int, default=DEFAULT_MAX_WINDOW)

    p = sub.add_parser('add')
    p.add_argument('tx_id')
    p.add_argument('--name')
    p.add_argument('--title')
    p.add_argument('--notes')
    p.add_argument('--back', type=int, default=DEFAULT_BLOCKS_BACK)
    p.add_argument('--after', type=int, default=DEFAULT_BLOCKS_AFTER)
    p.add_argument('--max-window', type=int, default=DEFAULT_MAX_WINDOW)

    p = sub.add_parser('report')
    p.add_argument('names', nargs='*')

    p = sub.add_parser('rerecord')
    p.add_argument('names', nargs='*')

    p = sub.add_parser('approve')
    p.add_argument('names', nargs='+')

    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    async with aiohttp.ClientSession() as session:
        src = None
        if args.command in ('find', 'add', 'rerecord'):
            src = Sources(Config(), session)
            await src.init()
        command = {'find': cmd_find, 'add': cmd_add, 'rerecord': cmd_rerecord, 'report': cmd_report,
                   'approve': cmd_approve}[args.command]
        await command(src, args)


if __name__ == '__main__':
    asyncio.run(main())
