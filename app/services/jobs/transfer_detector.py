from typing import List

from proto import NativeThorTx, parse_thor_address, DecodedEvent, thor_decode_amount_field
from proto.thor_types import MsgSend, MsgDeposit
from services.jobs.fetch.native_scan import BlockResult
from services.lib.constants import thor_to_float, is_rune
from services.lib.delegates import WithDelegates, INotified
from services.lib.money import Asset
from services.lib.utils import WithLogger
from services.models.transfer import RuneTransfer

DEFAULT_RUNE_FEE = 2000000


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
            memo = tx.tx.body.memo
            if not memo and hasattr(tx.first_message, 'memo'):
                memo = tx.first_message.memo

            for message in tx.tx.body.messages:
                comment = (type(message)).__name__
                if isinstance(message, MsgSend):
                    from_addr = self.address_parse(message.from_address)
                    to_addr = self.address_parse(message.to_address)
                    for coin in message.amount:
                        transfers.append(RuneTransfer(
                            from_addr=from_addr,
                            to_addr=to_addr,
                            block=block_no,
                            tx_hash=tx.hash,
                            amount=thor_to_float(coin.amount),
                            is_native=True,
                            asset=str(coin.denom).upper(),
                            comment=comment,
                            memo=memo,
                        ))
                elif isinstance(message, MsgDeposit):
                    for coin in message.coins:
                        transfers.append(RuneTransfer(
                            from_addr=self.address_parse(message.signer),
                            to_addr='',
                            block=block_no,
                            tx_hash=tx.hash,
                            amount=thor_to_float(coin.amount),
                            is_native=True,
                            asset=Asset(coin.asset.chain, coin.asset.symbol, is_synth=True).full_name,
                            comment=comment,
                            memo=memo,
                        ))
        return transfers

    async def on_data(self, sender, data):
        txs: List[NativeThorTx]
        txs, block_no = data
        transfers = self.process_block(txs, block_no)
        await self.pass_data_to_listeners(transfers)


class RuneTransferDetectorBlockEvents(WithDelegates, INotified):
    async def on_data(self, sender, data):
        events: List[DecodedEvent]
        events, block_no = data

        if not events:
            return

        transfers = []
        for event in events:
            if event.type == 'transfer':
                amount, asset = event.attributes['amount']
                transfers.append(RuneTransfer(
                    event.attributes['sender'],
                    event.attributes['recipient'],
                    block=block_no,
                    tx_hash='',
                    amount=thor_to_float(amount),
                    usd_per_asset=1.0,
                    is_native=True,
                    asset=asset.upper()
                ))
        await self.pass_data_to_listeners(transfers)


class RuneTransferDetectorFromTxResult(WithDelegates, INotified):
    async def on_data(self, sender, data: List[tuple]):
        transfers = []
        for tx_result, events, height in data:
            senders = events.get('transfer.sender')
            recipients = events.get('transfer.recipient')
            amounts = events.get('transfer.amount')

            if not all((senders, recipients, amounts)):
                continue

            tx_hash = events['tx.hash'][0]
            for sender, recipient, amount_obj in zip(senders, recipients, amounts):
                amount, asset = thor_decode_amount_field(amount_obj)

                # ignore fee transfers
                if is_fee_tx(amount, asset, recipient, self.reserve_address):
                    continue

                transfers.append(RuneTransfer(
                    sender, recipient,
                    height, tx_hash,
                    thor_to_float(amount),
                    asset=asset,
                    is_native=True
                ))

        await self.pass_data_to_listeners(transfers)

    def __init__(self, reserve_address=''):
        super().__init__()
        self.reserve_address = reserve_address


def is_fee_tx(amount, asset, to_addr, reserve_address):
    return amount == DEFAULT_RUNE_FEE and asset.lower() == 'rune' and to_addr == reserve_address


# This one is presently used!
class RuneTransferDetectorTxLogs(WithDelegates, INotified, WithLogger):
    DEFAULT_RESERVE_ADDRESS = 'thor1dheycdevq39qlkxs2a6wuuzyn4aqxhve4qxtxt'

    def __init__(self, reserve_address=None):
        super().__init__()
        self.reserve_address = reserve_address or self.DEFAULT_RESERVE_ADDRESS
        self.tx_proc = RuneTransferDetectorNativeTX()


    @staticmethod
    def _build_transfer_from_event(ev: DecodedEvent, block_no):
        if ev.type == 'outbound' and ev.attributes.get('chain') == 'THOR':
            asset = ev.attributes.get('asset', '')
            if is_rune(asset):
                asset = 'THOR.RUNE'
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
                for log in logs:
                    for ev in log['events']:
                        dec_ev = DecodedEvent.from_dict(ev)
                        if t := self._build_transfer_from_event(dec_ev, r.block_no):
                            transfers.append(t)
        except (TypeError, KeyError, ValueError) as e:
            self.logger.exception(f'Error processing tx logs {e}', stack_info=True)

        return transfers

    async def on_data(self, sender, data: BlockResult):
        if not data.tx_logs:
            return

        transfers = self.process_events(data)

        if transfers:
            self.logger.info(f'Detected {len(transfers)} transfers at block #{data.block_no}.')
        await self.pass_data_to_listeners(transfers)
