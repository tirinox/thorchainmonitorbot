from collections import Counter
import random

from tools.debug.dbg_cex_flow import _build_day_offsets, _build_fake_rune_transfer


def test_build_day_offsets_distributes_more_transfers_than_days_evenly():
    rng = random.Random(1337)

    day_offsets = _build_day_offsets(rng, days=14, transfer_count=80)

    assert len(day_offsets) == 80
    assert min(day_offsets) == 0
    assert max(day_offsets) == 13

    counts = Counter(day_offsets)
    assert len(counts) == 14
    assert set(counts.values()) <= {5, 6}


def test_build_fake_rune_transfer_can_make_peer_to_peer():
    rng = random.Random(1337)

    transfer = _build_fake_rune_transfer(
        rng,
        cex_list=['thor1cexdebugaddr'],
        ts=1_700_000_000,
        idx=1,
        transfer_kind='peer_to_peer',
    )

    assert transfer.from_addr.startswith('thor1debugfrom')
    assert transfer.to_addr.startswith('thor1debugto')
    assert transfer.from_addr != transfer.to_addr
    assert transfer.comment == 'debug fake peer_to_peer transfer'
    assert transfer.tx_hash == 'debug-fake-rune-transfer-peer_to_peer-001'

