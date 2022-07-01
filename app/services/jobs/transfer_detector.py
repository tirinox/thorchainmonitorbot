from typing import List

from proto import NativeThorTx, parse_thor_address, DecodedEvent, thor_decode_amount_field
from proto.thor_types import MsgSend, MsgDeposit
from services.lib.constants import thor_to_float
from services.lib.delegates import WithDelegates, INotified
from services.lib.money import Asset
from services.models.transfer import RuneTransfer


class RuneTransferDetectorNativeTX(WithDelegates, INotified):
    def __init__(self, address_prefix='thor'):
        super().__init__()
        self.address_prefix = address_prefix

    def address_parse(self, raw_address):
        return parse_thor_address(raw_address, self.address_prefix)

    async def on_data(self, sender, data):
        txs: List[NativeThorTx]
        txs, block_no = data

        if not txs:
            return
        transfers = []
        for tx in txs:
            for message in tx.tx.body.messages:
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
                            asset=coin.denom
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
                            asset=Asset(coin.asset.chain, coin.asset.symbol, is_synth=True).full_name
                        ))

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
                    usd_per_rune=1.0,
                    is_native=True,
                    asset=asset
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
    return amount == 2000000 and asset.lower() == 'rune' and to_addr == reserve_address


class RuneTransferDetectorTxLogs(WithDelegates, INotified):
    IGNORE_EVENTS = (
        'coin_spent',
        'coin_received',
        'fee',
        'transfer'
    )

    @staticmethod
    def _parse_transfers(transfer_attributes: list):
        d = {}
        results = []
        for attr in transfer_attributes:
            key = attr.get('key')
            value = attr.get('value')
            d[key] = value
            if 'recipient' in d and 'sender' in d and 'amount' in d:
                d['amount'], d['asset'] = thor_decode_amount_field(d['amount'])
                results.append(d)
                d = {}
        return results

    def _parse_one_tx(self, tx_log, block_no):
        ev_map = {
            ev['type']: ev['attributes'] for ev in tx_log
        }

        # join all interesting events' names
        comment = ", ".join([name for name in ev_map.keys() if name not in self.IGNORE_EVENTS])

        results = []
        if 'transfer' in ev_map:
            for transfer in self._parse_transfers(ev_map['transfer']):
                results.append(RuneTransfer(
                    from_addr=transfer['sender'],
                    to_addr=transfer['recipient'],
                    block=block_no,
                    tx_hash='',
                    amount=thor_to_float(transfer['amount']),
                    asset=transfer['asset'],
                    comment=comment
                ))

        return results

    def process_events(self, events, block_no):
        transfers = []
        for raw in events:
            try:
                this_transfers = self._parse_one_tx(raw[0]['events'], block_no)
                if this_transfers:
                    transfers.extend(this_transfers)
            except (KeyError, ValueError):
                raise
        return transfers

    async def on_data(self, sender, data):
        events, block_no = data

        if not events:
            return

        transfers = self.process_events(events, block_no)
        await self.pass_data_to_listeners(transfers)
