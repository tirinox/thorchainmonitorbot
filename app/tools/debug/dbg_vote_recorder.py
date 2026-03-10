import asyncio
import json
import logging
import random
import time
from datetime import datetime

import copy

from api.aionode.types import ThorMimirVote
from jobs.fetch.mimir import ConstMimirFetcher, MimirFetcherHistory
from jobs.runeyield.date2block import DateToBlockMapper
from jobs.vote_recorder import VoteRecorder
from lib.constants import THOR_BLOCK_TIME
from lib.date_utils import DAY
from lib.delegates import INotified, WithDelegates
from lib.texts import sep
from lib.utils import parallel_run_in_groups
from models.mimir import MimirHolder, AlertMimirVoting, MimirTuple
from models.mimir_naming import MIMIR_DICT_FILENAME
from notify.public.voting_notify import VotingNotifier
from tools.lib.lp_common import LpAppFramework


class FakeVoteInjector(INotified, WithDelegates):
    """
    Debug middleware: sits between ConstMimirFetcher and the rest of the chain.
    On every tick it randomly shuffles a few synthetic votes to make the
    vote-progress chart interesting without needing real network traffic.

    Parameters
    ----------
    keys          : mimir keys to inject votes on (all present ones if None)
    max_extra     : maximum extra synthetic signers to add per option
    flip_chance   : probability (0-1) that a random node switches its vote this tick
    """

    def __init__(self,
                 keys: list[str] | None = None,
                 max_extra: int = 8,
                 flip_chance: float = 0.3):
        super().__init__()
        self.keys = keys        # None → inject on every key found in the tuple
        self.max_extra = max_extra
        self.flip_chance = flip_chance

    def _inject(self, data: MimirTuple, active_signers: list[str]) -> MimirTuple:
        active_signers = [signer for signer in active_signers if signer]
        if not active_signers:
            print('[FakeVoteInjector] no active node signers available, skipping injection')
            return data

        # collect which keys to mess with
        present_keys = list({v.key for v in data.votes})
        target_keys = self.keys if self.keys else present_keys
        if not target_keys:
            return data

        extra_votes: list[ThorMimirVote] = []
        changes: list[str] = []

        for key in target_keys:
            key_votes = [v for v in data.votes if v.key == key]
            options = list({v.value for v in key_votes})
            if not options:
                options = [1, 2]

            existing_votes_by_signer = {
                vote.singer: vote
                for vote in key_votes
                if vote.singer in active_signers
            }
            eligible_signers = active_signers[:]
            random.shuffle(eligible_signers)
            eligible_signers = eligible_signers[:min(self.max_extra, len(eligible_signers))]

            for signer in eligible_signers:
                existing = existing_votes_by_signer.get(signer)
                if existing and random.random() > self.flip_chance:
                    continue

                weights = [max(1, self.max_extra - j * 2) for j in range(len(options))]
                chosen = random.choices(options, weights=weights, k=1)[0]

                if existing and existing.value == chosen:
                    continue

                new_vote = ThorMimirVote(key=key, value=chosen, singer=signer)
                extra_votes.append(new_vote)

                prev = existing.value if existing else '—'
                changes.append(f"  {key}  signer={signer}  {prev} → {chosen}")

        if changes:
            print(f"[FakeVoteInjector] {len(changes)} active-node synthetic vote change(s):")
            for line in changes:
                print(line)
        else:
            print(f"[FakeVoteInjector] no changes this tick ({len(active_signers)} active signers, {len(target_keys)} key(s))")

        if not extra_votes:
            return data

        untouched_votes = [
            vote for vote in data.votes
            if (vote.key, vote.singer) not in {(vote.key, vote.singer) for vote in extra_votes}
        ]

        new_data = copy.copy(data)
        object.__setattr__(new_data, 'votes', untouched_votes + extra_votes)
        return new_data

    async def on_data(self, sender, data: MimirTuple):
        nodes = await sender.deps.node_cache.get()
        active_signers = [node.node_address for node in nodes.active_nodes if node.node_address]
        patched = self._inject(data, active_signers)
        await self.pass_data_to_listeners(patched, sender=sender)


async def dbg_vote_recorder_continuous(app: LpAppFramework):
    d = app.deps
    mimir_fetcher = ConstMimirFetcher(d)

    vote_recorder = VoteRecorder(d)
    mimir_fetcher.add_subscriber(vote_recorder)

    await mimir_fetcher.run()


async def dbg_vote_record_from_past(app: LpAppFramework, overwrite=False):
    d = app.deps
    # mimir_fetcher = ConstMimirFetcher(d)

    vote_recorder = VoteRecorder(d)
    app.deps.mimir_cache.step_sleep = 0.01

    last_block = await app.deps.last_block_cache.get_thor_block()
    past_block = last_block - int(10 * DAY / THOR_BLOCK_TIME)
    # interval = (last_block - past_block) // 10
    interval = 100

    async def process_one_block(block):
        mimir_tuple = await app.deps.mimir_cache.get(height=block, forced=True)
        await vote_recorder.on_data(sender=None, data=mimir_tuple)

    tasks = [process_one_block(block) for block in reversed(range(past_block, last_block, interval))]
    await parallel_run_in_groups(tasks, 10, use_tqdm=True)


async def dbg_print_recent_changes(app: LpAppFramework):
    d = app.deps
    vote_recorder = VoteRecorder(d)

    active_nodes = await app.deps.node_cache.get_active_node_count()

    history = await vote_recorder.get_recent_progress(DAY * 30, active_nodes)
    if len(history) < 2:
        print('Not enough history yet')
        return

    prev_state = None
    for ts in sorted(history):
        if prev_state is None:
            prev_state = history[ts]
            continue

        voting_items = history[ts]
        for voting in voting_items:
            prev_voting = next((v for v in prev_state if v.key == voting.key), None)
            if not prev_voting:
                print(f'New voting: {voting.key} at {datetime.fromtimestamp(ts)}')
            else:
                for option in voting.options.values():
                    prev_option = prev_voting.options.get(option.value)
                    if not prev_option:
                        print(f'New option: {option.value} for voting {voting.key} at {datetime.fromtimestamp(ts)}')
                    elif prev_option.progress != option.progress:
                        print(
                            f'Progress changed for {option.value} in voting {voting.key} at {datetime.fromtimestamp(ts)}: {prev_option.progress:.2f}% -> {option.progress:.2f}%')
        prev_state = voting_items


async def dbg_vote_retrieve(app: LpAppFramework, key="HALTSIGNINGSOL"):
    d = app.deps
    vote_recorder = VoteRecorder(d)

    active_nodes = await app.deps.node_cache.get_active_node_count()
    mimir = await app.deps.mimir_cache.get_mimir_holder()

    history = await vote_recorder.get_key_progress(key, 14 * DAY, active_nodes)

    last_ts = max(history)
    alert = AlertMimirVoting(mimir, history[last_ts], None, history)

    sep()
    r = alert.to_dict(app.deps.loc_man.default)
    print(r)
    sep()
    print(json.dumps(r, indent=2))


async def dbg_time_discovery_single(app: LpAppFramework, block: int):
    dbm = DateToBlockMapper(app.deps)
    t0 = time.monotonic()
    dt = await dbm.get_datetime_by_block_height(block)
    t1 = time.monotonic()

    real_ts = await dbm.get_timestamp_by_block_height_precise(block)
    off_time = abs(real_ts - dt.timestamp())

    print(f"Block {block} -> {dt} (took {t1 - t0:.2f} seconds), off by {off_time:.2f} seconds)")

    return {
        "block": block,
        "datetime": dt,
        "time_taken": t1 - t0,
        "off_time": off_time,
        "real_ts": real_ts,
        "estimated_ts": dt.timestamp(),
        "real_dt": datetime.fromtimestamp(real_ts),
        "estimated_dt": dt,
    }


async def dbg_time_discovery_benchmark(app: LpAppFramework, n_tests=100):
    last_thor_block = await app.deps.last_block_cache.get_thor_block()
    past_thor_block = last_thor_block - 1_000_000
    for i in range(n_tests):
        block = random.randint(past_thor_block, last_thor_block)
        await dbg_time_discovery_single(app, block)


async def dbg_vote_continuous_monitor(app: LpAppFramework):
    """
    Continuously poll mimir, record every snapshot and print a line whenever
    any option's vote count changes.  Wires the real pipeline:

        ConstMimirFetcher
            → MimirHolder        (updates the in-memory mimir state)
            → VoteRecorder       (persists snapshots to Redis accumulator)
            → VotingNotifier     (detects changes, emits AlertMimirVoting)
            → _PrintSubscriber   (pretty-prints to console)
    """
    d = app.deps

    # ── mimir holder (keeps current state for VotingNotifier) ────────────────
    holder = MimirHolder()
    holder.mimir_rules.load(MIMIR_DICT_FILENAME)
    d.mimir_const_holder = holder          # VotingNotifier reads this from deps

    # ── notifier ─────────────────────────────────────────────────────────────
    voting_notifier = VotingNotifier(d)
    voting_notifier.add_subscriber(d.alert_presenter)
    voting_notifier.notification_cd_time = 60

    # ── console subscriber ────────────────────────────────────────────────────
    class _PrintSubscriber(INotified):
        async def on_data(self, sender, alert: AlertMimirVoting):
            sep()
            key         = alert.voting.key
            pretty      = alert.pretty_name or key
            opt         = alert.triggered_option
            active      = alert.voting.active_nodes
            units       = holder.mimir_rules.get_mimir_units(key)
            loc         = d.loc_man.default
            decoded_val = loc.format_mimir_value(key, opt.value, units=units) if opt else '?'

            print(
                f"[MIMIR VOTE CHANGE]  {pretty}  ({key})\n"
                f"  option  : {opt.value!r}  →  {decoded_val}\n"
                f"  signers : {opt.signer_count} / {active}"
                f"  ({opt.progress:.1f}%)\n"
                f"  top options: "
                + ", ".join(
                    f"{o.value}={o.signer_count}"
                    for o in alert.voting.top_options
                )
            )
            sep()

    voting_notifier.add_subscriber(_PrintSubscriber())

    # ── fetcher pipeline ──────────────────────────────────────────────────────
    current_height = await d.last_block_cache.get_thor_block()
    mimir_fetcher = MimirFetcherHistory(d, current_height - 20000, step=1000, sleep_period=0.1)

    # Debug middleware: inject random extra votes so the chart has movement.
    # Remove / comment out for production-like behaviour.
    fake_injector = FakeVoteInjector(
        keys=["NEXTCHAIN"],        # None = all keys; or e.g. ['NEXTCHAIN', 'HALTBNBCHAIN']
        max_extra=8,      # up to 8 extra synthetic signers per option
        flip_chance=0.25, # 25% chance each fake node switches its vote per tick
    )
    mimir_fetcher.add_subscriber(fake_injector)

    # downstream subscribers hang off fake_injector instead of directly on fetcher
    fake_injector.add_subscriber(holder)
    fake_injector.add_subscriber(voting_notifier.vote_recorder)
    fake_injector.add_subscriber(voting_notifier)

    print("Starting continuous mimir vote monitor. Press Ctrl+C to stop.")
    await mimir_fetcher.run()


async def dbg_mimir_at_block(app: LpAppFramework):
    last_block = await app.deps.last_block_cache.get_thor_block()
    print('last_block', last_block)
    past_block = last_block - 1000
    mimir_tuple = await app.deps.mimir_cache.get(height=past_block)
    print('mimir_tuple', mimir_tuple)

    sep()
    dbm = DateToBlockMapper(app.deps)
    block_ts = await dbm.get_timestamp_by_block_height_precise(past_block)
    print('block_ts', block_ts, datetime.fromtimestamp(block_ts))





async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        # await dbg_mimir_at_block(app)
        # await dbg_time_discovery_single(app, 24703873)
        # await dbg_time_discovery_benchmark(app, 300)
        # await dbg_vote_record_from_past(app)
        # await dbg_vote_retrieve(app, "NEXTCHAIN")
        # await dbg_print_recent_changes(app)
        await dbg_vote_continuous_monitor(app)


if __name__ == '__main__':
    asyncio.run(main())
