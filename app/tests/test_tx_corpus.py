"""
Replays the real transactions of tests/regression/tx_corpus through the bot's detectors and notifiers, offline,
and checks the swap the bot built against Midgard's and THORNode's truth and whether it was posted.
Add and review cases with tools/tx_corpus.py.
"""
import pytest

from tests.regression.harness import case_paths, case_name, load_case, replay_case, summarize_swap, alerts_of, \
    diff_swap

CASES = case_paths()


@pytest.mark.asyncio
@pytest.mark.parametrize('path', CASES, ids=[case_name(p) for p in CASES])
async def test_tx_corpus_case(path):
    case = load_case(path)
    tx_id = case['tx_id']
    result = await replay_case(case)

    assert not result.tape_misses, f'THORNode requests missing on the tape, re-record the case: {result.tape_misses}'

    action = next((a for a in result.actions if a.tx_hash == tx_id), None)
    problems = diff_swap(case['expected']['swap'], summarize_swap(action) if action else None,
                         case.get('known_issues', {}))
    assert not problems, '\n'.join(problems)

    assert alerts_of(result, tx_id) == case['expected']['alerts']
