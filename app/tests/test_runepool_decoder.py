import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from jobs.scanner.block_result import BlockResult
from jobs.scanner.runepool import RunePoolEventDecoder
from models.memo import THORMemo, ActionType

# real mainnet txs: POOL-:10000:t:200 from block 28002237 and POOL+ from block 28005299
SAMPLE_BLOCK_PATH = Path(__file__).with_name('sample_data') / 'block-runepool.json'
WITHDRAW_TX = 'F53E5A794876200DE0A03EB95BD36B9B840DBA5AE3EA21391D56007F1096BF90'
DEPOSIT_TX = '6FA59F4F9199F506B9E9435430F0C4543E52690D00FD35E2B67733F813BEE19A'
USD_PER_RUNE = 2.0


class FakePoolCache:
    async def get_usd_per_rune(self):
        return USD_PER_RUNE


def _decoder():
    return RunePoolEventDecoder(SimpleNamespace(redis=None), FakePoolCache())


def _load_block(withdraw_memo=None):
    raw = json.loads(SAMPLE_BLOCK_PATH.read_text())
    if withdraw_memo:
        body = raw['txs'][0]['tx']['body']
        body['memo'] = body['messages'][0]['memo'] = withdraw_memo
    return BlockResult.load_block(raw, 28002237)


@pytest.mark.asyncio
async def test_deposit_and_withdraw_are_decoded():
    events = {e.tx_hash: e for e in await _decoder().on_data(None, _load_block())}
    assert set(events) == {WITHDRAW_TX, DEPOSIT_TX}

    deposit = events[DEPOSIT_TX]
    assert deposit.is_deposit
    assert deposit.actor == 'thor1zefaak4kl33zhd2h7s62yaf9zev0npzetjy8g0'
    assert deposit.amount == pytest.approx(89.13259688)
    assert deposit.usd_amount == pytest.approx(89.13259688 * USD_PER_RUNE)

    # POOL- deposits 0 RUNE, the amount comes from the rune_pool_withdraw event
    withdraw = events[WITHDRAW_TX]
    assert withdraw.is_withdrawal
    assert withdraw.actor == 'thor1e9825mykdqudpsfe20hty682kmkwg6yl5yar77'
    assert withdraw.amount == pytest.approx(9406.18214132)
    assert withdraw.memo.withdraw_portion_bp == 10000


@pytest.mark.asyncio
async def test_withdraw_without_affiliate_does_not_break_the_block():
    events = await _decoder().on_data(None, _load_block('POOL-:10000'))
    assert {e.tx_hash for e in events} == {WITHDRAW_TX, DEPOSIT_TX}


@pytest.mark.parametrize('memo, bp', [
    ('POOL-', 10000),
    ('POOL-:10000', 10000),
    ('POOL-:5000:thor1aff', 5000),
    ('POOL-:10000:t:200', 10000),
])
def test_runepool_withdraw_memo(memo, bp):
    parsed = THORMemo.parse_memo(memo)
    assert parsed.action == ActionType.RUNEPOOL_WITHDRAW
    assert parsed.withdraw_portion_bp == bp


@pytest.mark.parametrize('memo', [
    '=:BTC.BTC:bc1qxyz::t:abc',  # fee is not a number
    '=:BTC.BTC:bc1qxyz::a/b/c:1/2',  # affiliates and fees mismatch
    'POOL-:10000:t:5000',  # affiliate fee over the limit
])
def test_malformed_memo_with_no_raise_returns_none(memo):
    assert THORMemo.parse_memo(memo, no_raise=True) is None
    with pytest.raises(Exception):
        THORMemo.parse_memo(memo)
