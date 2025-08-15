import asyncio
import random
from itertools import cycle
from typing import List

from api.aionode.types import ThorMimir, ThorMimirVote
from comm.localization.eng_base import BaseLocalization
from comm.localization.languages import Language
from jobs.fetch.cap import CapInfoFetcher
from jobs.fetch.mimir import ConstMimirFetcher
from lib.depcont import DepContainer
from lib.var_file import var_file_loop
from models.mimir import AlertMimirVoting, MimirTuple
from models.mimir_naming import MIMIR_PAUSE_GLOBAL
from notify.public.mimir_notify import MimirChangedNotifier
from notify.public.voting_notify import VotingNotifier
from tools.lib.lp_common import LpAppFramework


def print_mimir(loc, app):
    texts = loc.text_mimir_info(app.deps.mimir_const_holder)
    for text in texts:
        print(text)


async def demo_cap_test(app: LpAppFramework):
    cap_fetcher = CapInfoFetcher(app.deps)
    r = await cap_fetcher.fetch()
    print(r)


async def demo_mimir_consensus(app: LpAppFramework):
    await app.deps.mimir_const_fetcher.run_once()


async def demo_voting(app: LpAppFramework):
    mimir_to_test = 'CHURNINTERVAL'.upper()
    # mimir_to_test = NEXT_CHAIN_KEY

    mm = app.deps.mimir_const_holder
    vot_man = mm.voting_manager
    voting = vot_man.find_voting(mimir_to_test)
    prev_state = await VotingNotifier(app.deps).read_prev_state()
    prev_voting = prev_state.get(voting.key)
    option = next(iter(voting.options.values()))
    # prev_progress = prev_voting.get(str(option.value))  # str(.), that's because JSON keys are strings

    mm.get_entry(mimir_to_test).real_value = 1213

    # loc: BaseLocalization = app.deps.loc_man.default
    for language in (Language.ENGLISH, Language.ENGLISH_TWITTER, Language.RUSSIAN):
        # for language in (Language.ENGLISH_TWITTER,):
        loc: BaseLocalization = app.deps.loc_man[language]
        await app.send_test_tg_message(loc.notification_text_mimir_voting_progress(
            AlertMimirVoting(mm, voting, option)
        ))

    # await app.deps.broadcaster.notify_preconfigured_channels(
    #     BaseLocalization.notification_text_mimir_voting_progress,
    #     app.deps.mimir_const_holder,
    #     NEXT_CHAIN_KEY, prev_progress, voting, option,
    # )

    # print(loc, app)


class MimirMockChangesFetcher(ConstMimirFetcher):
    VOTES = 'votes'
    GENERAL = 'general'
    AUTO_AUTO = 'auto_auto'
    MIMIR_FAILS = 'mimir_fails'
    PAUSE_GLOBAL = MIMIR_PAUSE_GLOBAL

    def __init__(self, deps: DepContainer, method: str):
        super().__init__(deps)
        self.method = method
        self.prev = None
        self.sleep_period = 3
        self.mock_active = True

    async def fetch(self) -> MimirTuple:
        results = await super().fetch()

        if not self.mock_active:
            print('Mock is inactive! Returning original results...')
            return results

        if self.method == self.VOTES:
            self._dbg_randomize_votes(results.votes)
        elif self.method == self.GENERAL:
            votes = self._dbg_randomize_votes(results.votes)
            mimir, node_mimir = self._dbg_randomize_mimir(results.mimir, results.node_mimir)
            results = results._replace(mimir=mimir, votes=votes)
        elif self.method == self.AUTO_AUTO:
            results = self._dbg_auto_to_auto(results)
        elif self.method == self.MIMIR_FAILS:
            results = await self._dbg_fail_to_get_mimir(results)
        elif self.method == self.PAUSE_GLOBAL:
            results = await self._dbg_pause_global(results)

        return results

    # ----- D E B U G    S T U F F -----

    def _dbg_randomize_votes(self, votes: List[ThorMimirVote]):
        # votes.append(MimirVote('LOVEME', 2, 'thor10vmz8d0qwvq5hw9susmf7nefka9usazzcvkeaj'))
        # votes.append(MimirVote('LOVEME', 2, 'thor125tlvrmxqxxldu7c7j5qeg7x90dau6fga50kh9'))
        # votes.append(MimirVote('LOVEME', 2, 'thor10697ffyya4fddsvpwj6crfwe06pxkxkmdl8kev'))
        votes.append(ThorMimirVote('ENABLESAVINGSVAULTS', 3, 'thor10f40m6nv7ulc0fvhmt07szn3n7ajd7e8xhghc3'))
        votes.append(ThorMimirVote('ENABLESAVINGSVAULTS', 2, 'thor10smhtnkaju9ng0cag5p986czp6vmqvnmnl90wh'))
        votes.append(ThorMimirVote('ENABLESAVINGSVAULTS', 2, 'thor12espg8k5fxqmclx9vyte7cducmmvrtxll40q7z'))
        return votes

    def _dbg_randomize_node_mimir_results(self, results):
        return results

    _dbg_wheel = cycle([0, 1, 0, 5825662, 0, 55555, 1])

    def _dbg_randomize_mimir(self, fresh_mimir: ThorMimir, node_mimir: dict):
        if random.uniform(0, 1) > 0.5:
            fresh_mimir.constants['DERIVEDDEPTHBASISPTS'] = "555"
        if random.uniform(0, 1) > 0.3:
            fresh_mimir.constants['DERIVEDDEPTHBASISPTS'] = "777"
        if random.uniform(0, 1) > 0.4:
            fresh_mimir.constants['DERIVEDDEPTHBASISPTS'] = 10000

        if random.uniform(0, 1) > 0.6:
            fresh_mimir.constants['NativeTransactionFee'] = 300000
        if random.uniform(0, 1) > 0.5:
            fresh_mimir.constants['EVMDISABLECONTRACTWHITELIST'] = 0 if random.uniform(0, 1) > 0.5 else 1

        # if random.uniform(0, 1) > 0.3:
        #     try:
        #         del fresh_mimir.constants['NativeTransactionFee']
        #     except KeyError:
        #         pass
        # del fresh_mimir.constants["HALTBNBTRADING"]
        # fresh_mimir.constants["HALTETHTRADING"] = 0
        # fresh_mimir.constants["HALTBNBCHAIN"] = 1233243  # 1234568
        # del fresh_mimir.constants["EMISSIONCURVE"]
        # fresh_mimir.constants['NATIVETRANSACTIONFEE'] = 4000000
        # fresh_mimir.constants['MAXLIQUIDITYRUNE'] = 10000000000000 * random.randint(1, 99)
        # fresh_mimir.constants["FULLIMPLOSSPROTECTIONBLOCKS"] = 9000
        # fresh_mimir.constants["LOVEADMIN"] = 23

        # curr = fresh_mimir.constants["SOLVENCYHALTETHCHAIN"] = next(self._dbg_wheel)
        # print(f'SOLVENCYHALTETHCHAIN = {curr}')

        return fresh_mimir, node_mimir

    _dbg_wheel_auto_auto = cycle([0, 1, 0, 5825662, 5825562, 55555, 1])

    def _dbg_auto_to_auto(self, results: MimirTuple):
        key = 'HALTBNBTRADING'

        self.prev = results.mimir.constants[key]
        current = results.mimir.constants[key] = next(self._dbg_wheel)
        print(f'Mock: Mimir {key!r} | {self.prev} => {current}!')

        return results

    async def _dbg_fail_to_get_mimir(self, r: MimirTuple):
        return r._replace(mimir=ThorMimir({}))

    async def _dbg_pause_global(self, r: MimirTuple):

        key = MIMIR_PAUSE_GLOBAL
        self.prev = r.mimir.constants[key]
        thor_block = await self.deps.last_block_cache.get_thor_block()
        next_block = thor_block + random.randint(10, 10000)

        current = r.mimir.constants[key] = next_block

        print(f'Mock: Mimir {key!r} | {self.prev} => {current}!')

        return r


async def demo_mimir_spam_filter(app: LpAppFramework, mode):
    mimir_fetcher = MimirMockChangesFetcher(app.deps, mode)
    mimir_fetcher.sleep_period = 5

    mimir_holder = app.deps.mimir_const_holder
    mimir_fetcher.add_subscriber(mimir_holder)

    mimir_notifier = MimirChangedNotifier(app.deps)
    mimir_fetcher.add_subscriber(mimir_notifier)
    mimir_notifier.add_subscriber(app.deps.alert_presenter)

    async def f_every_tick(*_):
        await mimir_fetcher.run_once()

    async def var_changed(_, curr):
        mimir_fetcher.mock_active = bool(curr.get('mimir_mock_active'))
        print(f'Mock active: {mimir_fetcher.mock_active}')

    await var_file_loop(var_changed, f_every_tick, sleep_time=5.0)


async def run():
    app = LpAppFramework()
    await app.prepare(brief=True)

    await app.deps.node_info_fetcher.run_once()
    await app.deps.mimir_const_fetcher.run_once()

    # await demo_cap_test(app)
    # await demo_mimir_consensus(app)
    # await demo_mimir_spam_filter(app, mode=MimirMockChangesFetcher.PAUSE_GLOBAL)
    # await demo_mimir_spam_filter(app, mode=MimirMockChangesFetcher.GENERAL)
    await demo_voting(app)


if __name__ == '__main__':
    asyncio.run(run())
