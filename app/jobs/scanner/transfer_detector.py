from collections import defaultdict
from typing import List

from jobs.scanner.block_result import ThorEvent
from jobs.scanner.native_scan import BlockResult
from jobs.scanner.tx import NativeThorTx
from lib.constants import thor_to_float, DEFAULT_RESERVE_ADDRESS, BOND_MODULE, DEFAULT_RUNE_FEE, \
    RUNE_DENOM, RUNE_SYMBOL, NATIVE_RUNE_SYMBOL
from lib.delegates import WithDelegates, INotified
from lib.utils import WithLogger
from models.asset import Asset, is_rune
from models.transfer import RuneTransfer


class RuneTransferDetectorNativeTX(WithLogger):
    """
    It handles MsgSend and MsgDeposit messages.
    """

    def __init__(self, address_prefix='thor'):
        super().__init__()
        self.address_prefix = address_prefix

    def process_block(self, txs: List[NativeThorTx], block_no):
        if not txs:
            return []
        transfers = []
        for tx in txs:
            # find out memo
            memo = tx.deep_memo

            # todo!
            for message in tx.messages:
                comment = message.type
                # todo: test if it works good for /cosmos.bank.v1beta1.MsgSend
                if message.is_send:
                    from_addr = message.get('from_address', '')
                    to_addr = message.get('to_address', '')

                    for coin in message.get('amount', []):
                        coin: dict
                        asset = str(coin.get('denom', ''))
                        if is_rune(asset):
                            asset = RUNE_SYMBOL
                        # do not announce
                        transfers.append(RuneTransfer(
                            from_addr=from_addr,
                            to_addr=to_addr,
                            block=block_no,
                            tx_hash=tx.tx_hash,
                            amount=thor_to_float(coin.get('amount', 0)),
                            is_native=True,
                            asset=asset,
                            comment=comment,
                            memo=memo,
                        ))
                elif message.type == message.MsgDeposit:
                    for coin in message.coins:
                        asset = Asset.from_string(coin.get('asset', ''))
                        transfers.append(RuneTransfer(
                            from_addr=message.get('signer', '?'),
                            to_addr='',
                            block=block_no,
                            tx_hash=tx.tx_hash,
                            amount=thor_to_float(coin.get('amount', 0)),
                            is_native=True,
                            asset=asset,
                            comment=comment,
                            memo=memo,
                        ))

        return transfers


def is_fee_tx(amount, asset, to_addr, reserve_address):
    return amount == DEFAULT_RUNE_FEE and asset.lower() == RUNE_DENOM and to_addr == reserve_address


class RuneTransferDetectorTxLogs(WithLogger):
    def __init__(self, reserve_address=None):
        super().__init__()
        self.reserve_address = reserve_address or DEFAULT_RESERVE_ADDRESS

    @staticmethod
    def _build_transfer_from_event(ev: ThorEvent, block_no):
        if ev.type == 'outbound' and ev.attrs.get('chain') == 'THOR':
            asset = ev.attrs.get('asset', '')
            if is_rune(asset):
                asset = NATIVE_RUNE_SYMBOL
            memo = ev.attrs.get('memo', '')

            if 'amount' in ev.attrs:
                amt = ev.attrs.get('amount', 0)
            else:
                coin = ev.attrs.get('coin', '')
                components = coin.split(' ')
                if len(components) == 2:
                    amt, asset = components
                else:
                    return

            return RuneTransfer(
                ev.attrs['from'],
                ev.attrs['to'],
                block=block_no,
                tx_hash=ev.attrs.get('in_tx_id', ''),
                amount=thor_to_float(amt),
                asset=asset,
                is_native=True,
                comment=ev.type,
                memo=memo,
            )

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

    def process_events(self, r: BlockResult):
        transfers = []

        # Second, add Protocol's Outbounds
        for ev in r.end_block_events:
            if t := self._build_transfer_from_event(ev, r.block_no):
                transfers.append(t)

        # Third, add inbound transfers from the Protocol from the TX logs
        try:
            for tx in r.txs:
                if not tx.events:  # may be None
                    continue
                for ev in tx.events:
                    if t := self._build_transfer_from_event(ev, r.block_no):
                        transfers.append(t)
        except (TypeError, KeyError, ValueError) as e:
            self.logger.exception(f'Error processing tx logs {e}', stack_info=True)

        # Fourth, merge some same TXs
        try:
            transfers = self.connect_transactions_together(transfers)
        except (TypeError, KeyError, ValueError) as e:
            self.logger.exception(f'Error merging transfers {e}', stack_info=True)

        return transfers


class RuneTransferDetector(WithDelegates, INotified, WithLogger):
    def __init__(self, reserve_address=None):
        super().__init__()

        self.tx_proc = RuneTransferDetectorNativeTX()
        self.log_proc = RuneTransferDetectorTxLogs(reserve_address)

    async def on_data(self, sender, data: BlockResult):
        if not data.txs or not data.begin_block_events:
            self.logger.debug(f'Empty block #{data.block_no}?')
            return

        transfers_tx = self.tx_proc.process_block(data.txs, data.block_no)
        transfers_logs = self.log_proc.process_events(data)

        transfers = transfers_tx + transfers_logs

        if transfers:
            self.logger.info(f'Detected total {len(transfers)} transfers at block #{data.block_no} '
                             f'({len(transfers_tx)} from TXs, {len(transfers_logs)} from logs).')
            await self.pass_data_to_listeners(transfers)
