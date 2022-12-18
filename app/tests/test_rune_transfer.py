import logging
from typing import List

import pytest

from services.jobs.fetch.native_scan import NativeScannerBlock
from services.jobs.transfer_detector import RuneTransferDetectorTxLogs
from services.models.transfer import RuneTransfer
from tools.lib.lp_common import LpAppFramework


@pytest.fixture(scope="module")
def fixture_app():
    app = LpAppFramework(log_level=logging.INFO)
    app.brief = True
    return app


async def get_transfers_from_block(app, block_index):
    scanner = NativeScannerBlock(app.deps)
    r = await scanner.fetch_one_block(block_index)
    parser = RuneTransferDetectorTxLogs()
    transfers = parser.process_events(r)
    return transfers


def find_transfer(transfers: List[RuneTransfer],
                  from_addr=None,
                  to_addr=None, rune_amount=None, memo=None,
                  tx_hash=None, comment=None):
    if from_addr is not None:
        transfers = [t for t in transfers if t.from_addr == from_addr]
    if to_addr is not None:
        transfers = [t for t in transfers if t.to_addr == to_addr]
    if rune_amount is not None:
        transfers = [t for t in transfers if t.amount == rune_amount]
    if memo is not None:
        transfers = [t for t in transfers if t.memo == memo]
    if tx_hash is not None:
        transfers = [t for t in transfers if t.tx_hash == tx_hash]
    if comment is not None:
        transfers = [t for t in transfers if t.comment == comment]
    return transfers


@pytest.mark.asyncio
async def test_8686879(fixture_app: LpAppFramework):
    # this block contains a simple send
    async with fixture_app:
        transfers = await get_transfers_from_block(fixture_app, 8686879)
        assert len(transfers)

        t0 = find_transfer(transfers,
                           rune_amount=100000,
                           memo='100497173',
                           from_addr='thor1ukwhpglu7yh2g2rw8h7jvee2r0fv0e90nyxv6v',
                           to_addr='thor1uz4fpyd5f5d6p9pzk8lxyj4qxnwq6f9utg0e7k',
                           comment='MsgSend')
        assert len(t0) == 1


@pytest.mark.asyncio
async def test_8686955_transfer_bond(fixture_app: LpAppFramework):
    # this block contains bond
    async with fixture_app:
        transfers = await get_transfers_from_block(fixture_app, 8686955)
        assert len(transfers)
        t_bond = find_transfer(transfers,
                               rune_amount=108125,
                               from_addr='thor12msae5csjsvcd985n9nnp0xh7r6k8xm3xj69qe',
                               tx_hash='D4D45BB58292D47669ACECC43F8A90CF8EDD5E5F54629A80708248A9DD3712C2',
                               memo='BOND:thor12msae5csjsvcd985n9nnp0xh7r6k8xm3xj69qe:thor12msae5csjsvcd985n9nnp0xh7r6k8xm3xj69qe',
                               comment='MsgDeposit')
        assert len(t_bond) == 1
