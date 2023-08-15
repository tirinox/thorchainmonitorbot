from typing import List, Optional

from proto.access import parse_thor_address, NativeThorTx
from proto.types import MsgDeposit, MsgObservedTxIn
from services.jobs.fetch.native_scan import BlockResult
from services.lib.constants import thor_to_float, NATIVE_RUNE_SYMBOL
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.memo import THORMemo
from services.lib.money import Asset
from services.lib.texts import sep
from services.lib.utils import WithLogger
from services.models.s_swap import parse_swap_and_out_event, EventOutbound, StreamingSwap, EventSwapStart
from services.models.tx import ThorTx, ThorTxType, ThorMetaSwap, SUCCESS


class SwapStartDetector(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    def make_ss_event(self, msg, tx_hash, height) -> Optional[EventSwapStart]:
        ph = self.deps.price_holder

        memo = THORMemo.parse_memo(msg.memo)

        # Must be a swap!
        if not memo or memo.action != ThorTxType.TYPE_SWAP:
            return

        if msg.coins:
            out_asset = ph.pool_fuzzy_first(memo.asset)
            if not out_asset:
                self.logger.warning(f'{memo.asset}: asset not found!')
                return

            in_amount = thor_to_float(msg.coins[0].amount)
            in_asset = Asset.from_coin(msg.coins[0])

            if str(in_asset) == NATIVE_RUNE_SYMBOL:
                volume_usd = in_amount * ph.usd_per_rune
            else:
                in_pool_name = ph.pool_fuzzy_first(in_asset.native_pool_name)
                if not in_pool_name:
                    self.logger.warning(f'{in_asset.native_pool_name}: pool if inbound asset not found!')
                    return

                in_pool_info = ph.find_pool(in_pool_name)
                volume_usd = in_amount * in_pool_info.usd_per_asset

            if hasattr(msg, 'from_address'):
                from_address = msg.from_address
            else:
                from_address = parse_thor_address(msg.signer)

            return EventSwapStart(
                StreamingSwap(
                    tx_hash,
                    memo.s_swap_interval,
                    memo.s_swap_quantity,
                    0, 0, memo.limit, 0, 0, 0, [], []
                ),
                from_address=from_address,
                in_amount=thor_to_float(msg.coins[0].amount),
                in_asset=str(in_asset),
                out_asset=out_asset,
                expected_rate=thor_to_float(memo.limit),
                volume_usd=volume_usd,
                block_height=height
            )

    def handle_deposits(self, txs: List[NativeThorTx], height):
        results = []
        for tx in txs:
            try:
                msg: MsgDeposit = tx.first_message
                if event := self.make_ss_event(msg, tx.hash, height):
                    results.append(event)
            except Exception as e:
                self.logger.error(f'Could not parse DepositTx TX ({tx.hash}): {e!r}')

        return results

    def handle_observed_txs(self, txs: List[NativeThorTx], height):
        # Filter only unique MsgObservedTxIn
        hash_to_tx = {}
        for tx in txs:
            for observed_tx in tx.first_message.txs:
                if (tx_id := observed_tx.tx.id) not in hash_to_tx:
                    hash_to_tx[tx_id] = observed_tx.tx
        txs = list(hash_to_tx.values())

        results = []
        for tx in txs:
            try:
                # Instead of Message there goes just Tx. For this particular test their attributes are compatible!
                if event := self.make_ss_event(tx, tx.id, height):
                    results.append(event)
            except Exception as e:
                self.logger.error(f'Could not parse Observed In TX ({tx.id}): {e!r}')
        return results

    def detect_swaps(self, b: BlockResult):
        deposits = b.find_tx_by_type(MsgDeposit)
        observed_in_txs = b.find_tx_by_type(MsgObservedTxIn)

        # they are based only on memo parsed (just intention, real swap quantity may differ)
        return self.handle_deposits(deposits, b.block_no) + self.handle_observed_txs(observed_in_txs, b.block_no)


class NativeActionExtractor(WithDelegates, INotified, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self._swap_detector = SwapStartDetector(deps)

    async def on_data(self, sender, block: BlockResult) -> List[ThorTx]:
        """
        Strategy
        Let's aggreagate all events grouped by TX ID (inbound tx hash)

        """

        new_swaps = self._swap_detector.detect_swaps(block)
        print(f"New swaps: {len(new_swaps)}")

        for ev in block.end_block_events:
            swap_ev = parse_swap_and_out_event(ev)
            if not swap_ev:
                continue

            # if isinstance(swap_ev, EventOutbound):
            #     print(swap_ev)

            tx_id = swap_ev.tx_id
            if tx_id == '026170F3A6E8EA8A9BA1DDBB106536390C086B64D8E157F31E65789A31841284':
                sep(swap_ev.__class__.__name__)
                print(tx_id)
                sep()
                print(swap_ev)
                sep()

        tx = ThorTx(
            date='',
            height='',
            type=ThorTxType.TYPE_SWAP,
            pools=[],
            in_tx=[],
            out_tx=[],
            meta_swap=ThorMetaSwap(
                liquidity_fee='0',
                network_fees=[],
                trade_slip='0',
                trade_target='0',
                affiliate_fee=0.0,
                memo='',
                affiliate_address='',
                streaming=StreamingSwap(
                    tx_id='',
                    interval=0,
                    quantity=0,
                    count=0,
                    last_height=0,
                    trade_target=0,
                    deposit=0,
                    in_amt=0,
                    out_amt=0,
                    failed_swaps=[],
                    failed_swap_reasons=[]
                )
            ),
            status=SUCCESS
        )

        return []  # todo
