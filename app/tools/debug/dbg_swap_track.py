"""
Try the personal swap tracker on real txs without Telegram: /track them for a fake user, then poll like the bot does.
Every message the tracker would send is printed instead.

    PYTHONPATH=. python tools/debug/dbg_swap_track.py <txid> [<txid> ...] [--polls N]
"""
import asyncio
import sys

from comm.localization.eng_base import EnglishLocalization
from lib.texts import sep
from notify.personal.swap_tracker import PersonalSwapTracker
from tools.lib.lp_common import LpAppFramework

USER = 'dbg-swap-track'


async def main(tx_ids, polls):
    app = LpAppFramework(emergency=False)
    async with app:
        d = app.deps
        await d.mimir_const_fetcher.run_once()
        if d.fetcher_chain_state:
            await d.fetcher_chain_state.run_once()

        tracker = d.swap_tracker = PersonalSwapTracker(d)
        loc = EnglishLocalization(d.cfg)

        async def print_instead_of_sending(channel, message, **_):
            sep()
            print(f'→ {channel.type}:{channel.name} [{message.msg_type}] photo={message.photo is not None}')
            print(message.text)
            return 'ok', True

        d.broadcaster.safe_send_message_rate = print_instead_of_sending

        r = await d.db.get_redis()
        for tx in tx_ids:
            tx = tracker.normalize_tx_id(tx)
            await r.delete(tracker.key(tx))  # a fresh start every run
            await r.srem(tracker.KEY_ACTIVE, tx)
            sep(f'/track {tx}')
            result = await tracker.track_by_hash(tx, USER)
            print(f'result: {result}\nreply: {loc.text_track_result(result, tx)}')

        for i in range(polls):
            await asyncio.sleep(tracker.sleep_period)
            active = await tracker.fetch()
            print(f'--- poll #{i + 1}: {active} active')
            if not active:
                break


if __name__ == '__main__':
    args = sys.argv[1:]
    n_polls = int(args[args.index('--polls') + 1]) if '--polls' in args else 10
    hashes = [a for a in args if not a.startswith('--') and not a.isdigit()]
    asyncio.run(main(hashes, n_polls))
