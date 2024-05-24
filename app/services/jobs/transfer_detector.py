from collections import defaultdict
from typing import List

from proto.access import NativeThorTx, parse_thor_address, DecodedEvent, thor_decode_amount_field
from proto.types import MsgSend, MsgDeposit
from services.jobs.scanner.native_scan import BlockResult
from services.lib.constants import thor_to_float, DEFAULT_RESERVE_ADDRESS, BOND_MODULE, DEFAULT_RUNE_FEE, \
    RUNE_DENOM, RUNE_SYMBOL, NATIVE_RUNE_SYMBOL
from services.lib.delegates import WithDelegates, INotified
from services.lib.money import Asset, is_rune
from services.lib.utils import WithLogger
from services.models.transfer import RuneTransfer


# This one is used as a helper for the main RuneTransferDetectorTxLogs
class RuneTransferDetectorNativeTX(WithDelegates, INotified):
    def __init__(self, address_prefix='thor'):
        super().__init__()
        self.address_prefix = address_prefix

    def address_parse(self, raw_address):
        return parse_thor_address(raw_address, self.address_prefix)

    def process_block(self, txs: List[NativeThorTx], block_no):
        if not txs:
            return []
        transfers = []
        for tx in txs:
            # find out memo
            memo = tx.memo

            for message in tx.tx.body.messages:
                comment = (type(message)).__name__
                if isinstance(message, MsgSend):
                    from_addr = self.address_parse(message.from_address)
                    to_addr = self.address_parse(message.to_address)

                    for coin in message.amount:
                        asset = str(coin.denom)
                        if is_rune(asset):
                            asset = RUNE_SYMBOL
                        # do not announce
                        transfers.append(RuneTransfer(
                            from_addr=from_addr,
                            to_addr=to_addr,
                            block=block_no,
                            tx_hash=tx.hash,
                            amount=thor_to_float(coin.amount),
                            is_native=True,
                            asset=asset,
                            comment=comment,
                            memo=memo,
                        ))
                elif isinstance(message, MsgDeposit):
                    for coin in message.coins:
                        asset = Asset.from_coin(coin).to_canonical
                        transfers.append(RuneTransfer(
                            from_addr=self.address_parse(message.signer),
                            to_addr='',
                            block=block_no,
                            tx_hash=tx.hash,
                            amount=thor_to_float(coin.amount),
                            is_native=True,
                            asset=asset,
                            comment=comment,
                            memo=memo,
                        ))
        return transfers

    async def on_data(self, sender, data):
        txs: List[NativeThorTx]
        txs, block_no = data
        transfers = self.process_block(txs, block_no)
        await self.pass_data_to_listeners(transfers)


def is_fee_tx(amount, asset, to_addr, reserve_address):
    return amount == DEFAULT_RUNE_FEE and asset.lower() == RUNE_DENOM and to_addr == reserve_address


# This one is presently used!
class RuneTransferDetectorTxLogs(WithDelegates, INotified, WithLogger):
    def __init__(self, reserve_address=None):
        super().__init__()
        self.reserve_address = reserve_address or DEFAULT_RESERVE_ADDRESS
        self.tx_proc = RuneTransferDetectorNativeTX()

    @staticmethod
    def _build_transfer_from_event(ev: DecodedEvent, block_no):
        if ev.type == 'outbound' and ev.attributes.get('chain') == 'THOR':
            asset = ev.attributes.get('asset', '')
            if is_rune(asset):
                asset = NATIVE_RUNE_SYMBOL
            memo = ev.attributes.get('memo', '')

            if 'amount' in ev.attributes:
                amt = ev.attributes.get('amount', 0)
            else:
                coin = ev.attributes.get('coin', '')
                components = coin.split(' ')
                if len(components) == 2:
                    amt, asset = components
                else:
                    return

            return RuneTransfer(
                ev.attributes['from'],
                ev.attributes['to'],
                block=block_no,
                tx_hash=ev.attributes.get('in_tx_id', ''),
                amount=thor_to_float(amt),
                asset=asset,
                is_native=True,
                comment=ev.type,
                memo=memo,
            )

    def process_events(self, r: BlockResult):
        transfers = []

        # First, Get transfers from incoming transactions
        transfers += self.tx_proc.process_block(r.txs, r.block_no)

        # Second, add Protocol's Outbounds
        for ev in r.end_block_events:
            if t := self._build_transfer_from_event(ev, r.block_no):
                transfers.append(t)

        # Third, add inbound transfers from the Protocol from the TX logs
        try:
            for logs in r.tx_logs:
                if not logs:  # may be None
                    continue
                for log in logs.entries:
                    for ev in log['events']:
                        dec_ev = DecodedEvent.from_dict(ev)
                        if t := self._build_transfer_from_event(dec_ev, r.block_no):
                            transfers.append(t)
        except (TypeError, KeyError, ValueError) as e:
            self.logger.exception(f'Error processing tx logs {e}', stack_info=True)

        # Fourth, merge some same TXs
        try:
            transfers = self.connect_transactions_together(transfers)
        except (TypeError, KeyError, ValueError) as e:
            self.logger.exception(f'Error merging transfers {e}', stack_info=True)

        return transfers

    async def on_data(self, sender, data: BlockResult):
        if not data.tx_logs:
            return

        transfers = self.process_events(data)

        if transfers:
            self.logger.info(f'Detected {len(transfers)} transfers at block #{data.block_no}.')
        await self.pass_data_to_listeners(transfers)

    @classmethod
    def connect_transactions_together(cls, transfers: List[RuneTransfer]):
        hash_map = defaultdict(list)
        for tr in transfers:
            if tr.tx_hash:
                hash_map[tr.tx_hash].append(tr)

        for same_hash_transfers in hash_map.values():
            cls.make_connection(same_hash_transfers)

        return transfers

    @staticmethod
    def set_comment(transfers: List[RuneTransfer], comment):
        for t in transfers:
            t.comment = comment

    @classmethod
    def make_connection(cls, transfers: List[RuneTransfer]):
        # some special cases
        if any(t.memo.lower().startswith('unbond:') for t in transfers):
            cls.set_comment(transfers, 'unbond')
            for t in transfers:
                if not t.from_addr:
                    t.from_addr = BOND_MODULE

        if any(t.memo.lower().startswith('bond:') for t in transfers):
            cls.set_comment(transfers, 'bond')
            for t in transfers:
                if not t.to_addr:
                    t.to_addr = BOND_MODULE
