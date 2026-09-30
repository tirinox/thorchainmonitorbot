"""
DEX aggregator debugging: find real swaps that went through a DEX aggregator and see how the alerts look.

Run from "app/" with PYTHONPATH=. (a YAML path as the first argument is the config, see lib/config.py):

  # 1) Find recent aggregator swaps (Midgard + real EVM RPC calls; results go to ../temp/dex_txs.json)
  python tools/debug/dbg_dex_aggregator.py find --pages 3 --max 10 --affiliate ts,rg,ll

  # 2) Render the alert texts (and the infographic with --pic) for given tx hashes or for the found ones
  python tools/debug/dbg_dex_aggregator.py show <HASH> [<HASH> ...] --pic
  python tools/debug/dbg_dex_aggregator.py show --from-file --pic --send

Nothing is broadcast to the real channels: texts are printed, pictures are saved to ../temp/,
and --send delivers them only to the Telegram test user.
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from io import BytesIO
from typing import List, Optional

from api.midgard.parser import get_parser_by_network_id
from api.midgard.urlgen import free_url_gen
from api.w3.aggregator import AggregatorDataExtractor, is_evm_tx_hash
from api.w3.token_record import AmountToken
from comm.localization.languages import Language
from comm.telegram.telegram import TG_TEST_USER
from jobs.volume_filler import VolumeFillerUpdater
from lib.constants import thor_to_float
from lib.date_utils import now_ts
from lib.money import DepthCurve
from lib.texts import sep
from models.memo import ActionType
from models.tx import ThorAction, EventLargeTransaction
from notify.channel import BoardMessage
from notify.public.tx_notify import SwapTxNotifier
from tools.lib.lp_common import LpAppFramework

OUT_DIR = '../temp'
FOUND_FILE = f'{OUT_DIR}/dex_txs.json'
LANGUAGES = (Language.ENGLISH, Language.RUSSIAN, Language.ENGLISH_TWITTER)


def leg_str(leg: Optional[AmountToken]) -> str:
    if not leg:
        return '-'
    amount = f'{leg.amount:.4f} ' if leg.has_amount else ''
    return f'{amount}{leg.chain}.{leg.symbol} via {leg.aggr_name or "?"} [{leg.source}]'


def describe(tx: ThorAction, usd_per_rune: float) -> str:
    memo = tx.memo
    return (
        f'{tx.tx_hash}\n'
        f'    date: {tx.date_timestamp}, age: {tx.age_sec / 3600:.1f} h, status: {tx.status}\n'
        f'    volume: ${tx.get_usd_volume(usd_per_rune):,.0f}\n'
        f'    memo: {memo.build() if memo else "?"}\n'
        f'    in : {tx.first_input_tx.first_asset if tx.first_input_tx else "?"}'
        f' ({tx.first_input_tx_hash})\n'
        f'    out: {tx.recipients_output.first_asset if tx.recipients_output else "?"}'
        f' ({tx.recipients_output.tx_id if tx.recipients_output else "?"})\n'
        f'    DEX in : {leg_str(tx.dex_info.swap_in)}\n'
        f'    DEX out: {leg_str(tx.dex_info.swap_out)}'
    )


class DexDebugger:
    def __init__(self, app: LpAppFramework, renderer_url: str = ''):
        self.app = app
        self.deps = app.deps
        self.extractor = AggregatorDataExtractor(self.deps)
        self.extractor.on_chain_out_min_usd = 0.0  # debug: always decode the outbound on-chain
        self.volume_filler = VolumeFillerUpdater(self.deps)
        self.notifier = SwapTxNotifier(self.deps, self.deps.cfg.tx.swap, curve=DepthCurve.default())
        self.tx_parser = get_parser_by_network_id(self.deps.cfg.network_id)
        if renderer_url:
            self.deps.alert_presenter.renderer.url = renderer_url

    @property
    def evm_gas_assets(self):
        return set(self.extractor.assets_to_trigger)

    async def process(self, txs: List[ThorAction]):
        await self.volume_filler.fill_volumes(txs)
        ph = await self.deps.pool_cache.get()
        for tx in txs:
            tx.dex_info = await self.extractor.detect(tx, ph)
        return ph

    async def load_tx(self, tx_hash: str) -> Optional[ThorAction]:
        j = await self.deps.midgard_connector.request(free_url_gen.url_for_tx(0, 50, txid=tx_hash))
        result = self.tx_parser.parse_tx_response(j)
        return result.txs[0] if result and result.txs else None

    # ---- find ----

    def memo_has_aggregator(self, tx: ThorAction) -> bool:
        try:
            memo = tx.memo
            return bool(memo and memo.uses_aggregator_out)
        except Exception:
            return False

    def has_evm_gas_input(self, tx: ThorAction) -> bool:
        in_tx = tx.first_input_tx
        return bool(in_tx and in_tx.first_asset in self.evm_gas_assets and is_evm_tx_hash(in_tx.tx_id))

    async def fetch_swaps(self, page: int, per_page: int, asset: str = '', affiliate: str = ''):
        url = free_url_gen.url_for_tx(page * per_page, per_page, tx_type=ActionType.SWAP, asset=asset or None)
        if affiliate:
            url += f'&affiliate={affiliate}'  # Midgard filters by affiliate name; aggregator users have their own
        j = await self.deps.midgard_connector.request(url)
        result = self.tx_parser.parse_tx_response(j) if isinstance(j, dict) else None
        return result.txs if result else []

    async def find(self, pages: int, max_found: int, max_rpc: int, asset: str = '', affiliates=()):
        """
        Sweep the swaps page by page. The swap-out leg is visible in the memo, so it costs nothing;
        the swap-in leg needs an RPC call per swap with an EVM gas asset on the input, so those are capped.
        Aggregator users (THORSwap "ts", Rango "rg", LiFi "ll") mark their swaps with an affiliate name,
        so sweeping by affiliate finds them much faster than the general flow.
        """
        per_page = int(self.deps.cfg.tx.tx_per_batch)
        found, seen = {}, set()
        rpc_used = 0
        oldest = None
        affiliates = list(affiliates) or ['']
        print(f'Sweeping {pages} pages of {per_page} swaps for affiliates {affiliates or "any"}'
              f'{" involving " + asset if asset else ""}; RPC budget: {max_rpc} lookups')

        queue = [(aff, page) for aff in affiliates for page in range(pages)]
        for aff, page in queue:
            if len(found) >= max_found:
                break
            txs = await self.fetch_swaps(page, per_page, asset, aff)
            if not txs:
                print(f'{aff or "*"} page {page}: nothing (Midgard error or the end)')
                continue
            batch_txs = txs
            fresh = [tx for tx in batch_txs if tx.tx_hash not in seen]
            seen.update(tx.tx_hash for tx in fresh)
            oldest = min(tx.date_timestamp for tx in fresh) if fresh else oldest

            memo_out = [tx for tx in fresh if self.memo_has_aggregator(tx)]
            evm_in = [tx for tx in fresh if tx not in memo_out and self.has_evm_gas_input(tx)]
            if rpc_used >= max_rpc:
                evm_in = []
            rpc_used += len(evm_in) + len(memo_out)

            candidates = memo_out + evm_in
            if candidates:
                ph = await self.process(candidates)
                for tx in candidates:
                    if tx.dex_aggregator_used:
                        found[tx.tx_hash] = tx
                        sep()
                        print(describe(tx, ph.usd_per_rune))
                        sep()

            age_h = (now_ts() - oldest) / 3600 if oldest else 0
            print(f'{aff or "*"} page {page}: {len(fresh)} swaps ({age_h / 24:.1f} d back), memo-out {len(memo_out)}, '
                  f'evm-in checked {len(evm_in)}, rpc used {rpc_used}/{max_rpc}, found {len(found)}')

        print(f'Found {len(found)} DEX aggregator swaps among {len(seen)} swaps')
        self.save_found(list(found.values()))
        return list(found.values())

    @staticmethod
    def save_found(txs: List[ThorAction]):
        os.makedirs(OUT_DIR, exist_ok=True)
        txs = sorted(txs, key=lambda t: t.full_volume_in_rune, reverse=True)
        data = [{
            'hash': tx.tx_hash,
            'date': tx.date_timestamp,
            'volume_rune': tx.full_volume_in_rune,
            'memo': tx.memo.build() if tx.memo else '',
            'swap_in': tx.dex_info.swap_in.as_json if tx.dex_info.swap_in else None,
            'swap_out': tx.dex_info.swap_out.as_json if tx.dex_info.swap_out else None,
        } for tx in txs]
        with open(FOUND_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        print(f'Saved {len(data)} txs to {FOUND_FILE}')

    @staticmethod
    def load_found_hashes() -> List[str]:
        with open(FOUND_FILE, 'r') as f:
            return [item['hash'] for item in json.load(f)]

    # ---- show ----

    async def show(self, tx_hashes: List[str], with_pic: bool, send: bool):
        presenter = self.deps.alert_presenter
        os.makedirs(OUT_DIR, exist_ok=True)

        for tx_hash in tx_hashes:
            sep()
            tx = await self.load_tx(tx_hash)
            if not tx:
                print(f'{tx_hash}: not found in Midgard')
                continue
            ph = await self.process([tx])
            print(describe(tx, ph.usd_per_rune))
            sep()

            event = EventLargeTransaction(tx, ph.usd_per_rune, ph.pool_info_map.get(tx.first_pool_l1))
            try:
                event = await self.notifier._event_transform(event)
            except Exception as e:
                print(f'Event transform failed (volumes/rapid swap stats): {e!r}')
            if not event.usd_volume_input or not event.usd_volume_output:
                # old swaps: the node has no state at their height, so price the legs with the current pools
                in_tx, out_tx = tx.first_input_tx, tx.recipients_output
                if in_tx:
                    event.usd_volume_input = ph.convert_to_usd(thor_to_float(in_tx.first_amount), in_tx.first_asset) or 0.0
                if out_tx:
                    event.usd_volume_output = ph.convert_to_usd(thor_to_float(out_tx.first_amount), out_tx.first_asset) or 0.0
            name_map = await presenter.load_names(tx.all_addresses)

            for lang in LANGUAGES:
                loc = self.deps.loc_man[lang]
                text = loc.notification_text_large_single_tx(event, name_map)
                print(f'[{lang}]\n{text}\n')

                photo = None
                if with_pic:
                    try:
                        photo, photo_name = await presenter.render_swap_finish(loc, event, name_map)
                    except Exception as e:
                        print(f'Picture rendering failed: {e!r}')
                    if photo:
                        path = f'{OUT_DIR}/dex_swap_{tx_hash[:8]}_{lang}.png'
                        with open(path, 'wb') as f:
                            f.write(photo)
                        print(f'Picture saved to {path}')

                if send:
                    await self.send_to_test_user(text, photo)

    async def send_to_test_user(self, text: str, photo: Optional[bytes]):
        if photo:
            msg = BoardMessage.make_photo(BytesIO(photo), text, 'swap_finished.png')
            await self.deps.telegram_bot.send_message(TG_TEST_USER, msg, parse_mode='HTML')
        else:
            await self.app.send_test_tg_message(text)


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--renderer', default='http://127.0.0.1:8404/render',
                        help='infographic renderer URL as seen from this machine ("" keeps the config value)')
    sub = parser.add_subparsers(dest='command', required=True)

    p_find = sub.add_parser('find', help='find recent swaps that used a DEX aggregator')
    p_find.add_argument('--pages', type=int, default=20, help='Midgard pages of swaps to sweep')
    p_find.add_argument('--max', type=int, default=10, help='stop after this many found')
    p_find.add_argument('--max-rpc', type=int, default=100, help='RPC budget for swap-in lookups')
    p_find.add_argument('--asset', default='', help='sweep only swaps involving this asset, e.g. ETH.ETH')
    p_find.add_argument('--affiliate', default='ts,rg,ll',
                        help='comma separated affiliate names to sweep ("" = all swaps)')

    p_show = sub.add_parser('show', help='render the alerts for the given swaps')
    p_show.add_argument('hashes', nargs='*', help='tx hashes (Midgard)')
    p_show.add_argument('--from-file', action='store_true', help=f'take the hashes from {FOUND_FILE}')
    p_show.add_argument('--pic', action='store_true', help='render the infographic (needs the renderer)')
    p_show.add_argument('--send', action='store_true', help='send the results to the Telegram test user')
    p_show.add_argument('--limit', type=int, default=5, help='at most this many txs from the file')
    return parser.parse_args(argv)


async def main():
    argv = sys.argv[1:]
    if argv and argv[0].lower().endswith(('.yaml', '.yml')):
        argv = argv[1:]  # the config path was taken by lib.config
    args = parse_args(argv)

    app = LpAppFramework(emergency=False, log_level=logging.WARNING)
    async with app:
        dbg = DexDebugger(app, renderer_url=args.renderer)
        if args.command == 'find':
            affiliates = [a.strip() for a in args.affiliate.split(',') if a.strip()]
            await dbg.find(args.pages, args.max, args.max_rpc, args.asset.strip().upper(), affiliates)
        elif args.command == 'show':
            hashes = list(args.hashes)
            if args.from_file:
                hashes += dbg.load_found_hashes()[:args.limit]
            if not hashes:
                print('No tx hashes given. Pass them as arguments or use --from-file after "find".')
                return
            await dbg.show(hashes, with_pic=args.pic, send=args.send)


if __name__ == '__main__':
    asyncio.run(main())
