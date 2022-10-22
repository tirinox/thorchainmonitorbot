import asyncio

from localization.eng_base import BaseLocalization
from localization.languages import Language
from services.jobs.fetch.cap import CapInfoFetcher
from services.notify.types.voting_notify import VotingNotifier
from tools.lib.lp_common import LpAppFramework


def print_mimir(loc, app):
    texts = loc.text_mimir_info(app.deps.mimir_const_holder)
    for text in texts:
        print(text)


async def demo_cap_test(app: LpAppFramework):
    cap_fetcher = CapInfoFetcher(app.deps)
    r = await cap_fetcher.fetch()
    print(r)


async def run():
    app = LpAppFramework()
    await app.prepare(brief=True)

    await demo_cap_test(app)
    return

    mimir_to_test = 'MaxSynthPerAssetDepth'.upper()
    # mimir_to_test = NEXT_CHAIN_KEY

    voting = app.deps.mimir_const_holder.voting_manager.find_voting(mimir_to_test)
    prev_state = await VotingNotifier(app.deps).read_prev_state()
    prev_voting = prev_state.get(voting.key)
    option = next(iter(voting.options.values()))
    prev_progress = prev_voting.get(str(option.value))  # str(.), that's because JSON keys are strings

    # loc: BaseLocalization = app.deps.loc_man.default

    for language in (Language.ENGLISH, Language.ENGLISH_TWITTER, Language.RUSSIAN):
        # for language in (Language.ENGLISH_TWITTER,):
        loc: BaseLocalization = app.deps.loc_man[language]
        await app.send_test_tg_message(loc.notification_text_mimir_voting_progress(
            app.deps.mimir_const_holder,
            mimir_to_test, prev_progress, voting, option,
        ))

    # await app.deps.broadcaster.notify_preconfigured_channels(
    #     BaseLocalization.notification_text_mimir_voting_progress,
    #     app.deps.mimir_const_holder,
    #     NEXT_CHAIN_KEY, prev_progress, voting, option,
    # )

    # print(loc, app)


if __name__ == '__main__':
    asyncio.run(run())
