import logging
from typing import List

import pytest

from jobs.scanner.native_scan import NativeScannerBlock
from jobs.transfer_detector import RuneTransferDetectorTxLogs
from lib.constants import thor_to_float
from lib.texts import sep
from models.transfer import RuneTransfer
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
                  to_addr=None, amount=None, memo=None,
                  asset=None,
                  tx_hash=None, comment=None, print_it=False):
    if from_addr is not None:
        transfers = [t for t in transfers if t.from_addr == from_addr]
        assert transfers, f"No transfers from {from_addr}"
    if to_addr is not None:
        transfers = [t for t in transfers if t.to_addr == to_addr]
        assert transfers, f"No transfers to {to_addr}"
    if amount is not None:
        transfers = [t for t in transfers if int(t.amount) == int(amount)]
        assert transfers, f"No transfers with amount {amount}"
    if asset is not None:
        transfers = [t for t in transfers if t.asset == asset]
        assert transfers, f"No transfers with asset {asset}"

    if memo is not None:
        transfers = [t for t in transfers if t.memo == memo]
        assert transfers, f"No transfers with memo {memo}"
    if tx_hash is not None:
        transfers = [t for t in transfers if t.tx_hash == tx_hash]
        assert transfers, f"No transfers with tx_hash {tx_hash}"
    if comment is not None:
        transfers = [t for t in transfers if t.comment == comment]
        assert transfers, f"No transfers with comment {comment}"

    if print_it:
        sep()
        for i, t in enumerate(transfers, start=1):
            print(f"{i:<4}. {t}")

    return transfers


@pytest.mark.asyncio
async def test_8686879(fixture_app: LpAppFramework):
    # this block contains a simple send
    async with fixture_app:
        transfers = await get_transfers_from_block(fixture_app, 8686879)
        assert len(transfers)

        t0 = find_transfer(transfers,
                           amount=100000,
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
        assert find_transfer(transfers,
                             amount=108125,
                             from_addr='thor12msae5csjsvcd985n9nnp0xh7r6k8xm3xj69qe',
                             tx_hash='D4D45BB58292D47669ACECC43F8A90CF8EDD5E5F54629A80708248A9DD3712C2',
                             memo='BOND:thor12msae5csjsvcd985n9nnp0xh7r6k8xm3xj69qe:thor12msae5csjsvcd985n9nnp0xh7r6k8xm3xj69qe',
                             comment='MsgDeposit')


@pytest.mark.asyncio
async def test_8783469_transfer_unbond(fixture_app: LpAppFramework):
    # this block contains unbond
    async with fixture_app:
        transfers = await get_transfers_from_block(fixture_app, 8783469)
        assert len(transfers)
        assert find_transfer(transfers,
                             amount=742_129.96,
                             to_addr='thor1j96ruj3h5qm8ldr9cg39ghvvlp344h0j803vq2',
                             tx_hash='6251CFC8214B72E7D1A5A3299445A861990C593707560983C85D054BBDB70DCA',
                             )


@pytest.mark.asyncio
async def test_8793017_swap_from_rune(fixture_app: LpAppFramework):
    async with fixture_app:
        transfers = await get_transfers_from_block(fixture_app, 8793017)
        assert len(transfers)
        assert find_transfer(transfers,
                             amount=3.059683,
                             from_addr='thor1dp6mdtrr54zs4us2nglkvelrsl7l2fdwe74wef',
                             tx_hash='D74DAC3110AD6B42A5F4AEDF74677C8AB9B778EBF035528CDCBFEEC4CDA9D70E',
                             )


@pytest.mark.asyncio
async def test_8799897_swap_from_rune(fixture_app: LpAppFramework):
    async with fixture_app:
        transfers = await get_transfers_from_block(fixture_app, 8799897)
        assert len(transfers)
        assert find_transfer(transfers,
                             amount=348,
                             from_addr='thor1ukwhpglu7yh2g2rw8h7jvee2r0fv0e90nyxv6v',
                             tx_hash='D5733DD67E22EB8809CE3BDB0283450BEA21CF23237A9D3681F40DED443553AD',
                             memo='SWAP:BTC/BTC:thor1ukwhpglu7yh2g2rw8h7jvee2r0fv0e90nyxv6v:2603279',
                             )


@pytest.mark.asyncio
async def test_8217619_transfer_big_simple(fixture_app: LpAppFramework):
    # many txs, there was a mess
    async with fixture_app:
        transfers = await get_transfers_from_block(fixture_app, 8217619)

        assert len(transfers)

        assert find_transfer(transfers,
                             amount=174508.40130779002,
                             from_addr='thor1uz4fpyd5f5d6p9pzk8lxyj4qxnwq6f9utg0e7k',
                             to_addr='thor1t60f02r8jvzjrhtnjgfj4ne6rs5wjnejwmj7fh',
                             memo='')

        assert find_transfer(transfers,
                             amount=thor_to_float(2557589206),
                             from_addr='thor1v8ppstuf6e3x0r4glqc68d5jqcs2tf38cg2q6y',
                             to_addr='thor1t2pfscuq3ctgtf5h3x7p6zrjd7e0jcvuszyvt5',
                             memo='OUT:ABDBC4B3F261A419E00D620B2574118574D543BF7288A783DCFBF882603BA558')


@pytest.mark.asyncio
async def test_8793184_swap_to_rune(fixture_app: LpAppFramework):
    async with fixture_app:
        transfers = await get_transfers_from_block(fixture_app, 8793184)
        assert len(transfers)

        # swap to rune is outbound comment
        assert find_transfer(transfers,
                             amount=2_855.49,
                             to_addr='thor1t3mkwu79rftp4uqf3xrpf5qwczp97jg9jul53p'
                             )


@pytest.mark.asyncio
async def test_8788705_send_synth(fixture_app: LpAppFramework):
    async with fixture_app:
        transfers = await get_transfers_from_block(fixture_app, 8788705)
        assert len(transfers)

        # swap to rune is outbound comment
        assert find_transfer(transfers,
                             amount=0.000272,
                             asset='BTC/BTC',
                             from_addr='thor1julaxd5473t0nvhj7uwvcts4806uvx0huxz0g3',
                             to_addr='thor1yqerp6r3wasqy20r6qsk9fpkg8pu8p6ctek7z3'
                             )


@pytest.mark.asyncio
async def test_8801498_debug_exc(fixture_app: LpAppFramework):
    async with fixture_app:
        transfers = await get_transfers_from_block(fixture_app, 8801498)
        assert len(transfers)
