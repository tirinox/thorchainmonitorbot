import base64
import hashlib
import inspect
import typing

import bech32
import betterproto

import proto.thor_types as thor_type_lib
from proto.cosmos.tx.v1beta1 import Tx


def parse_thor_address(addr: bytes, prefix='thor') -> str:
    good_bits = bech32.convertbits(list(addr), 8, 5, False)
    return bech32.bech32_encode(prefix, good_bits)


def register_thorchain_messages():
    result = {}
    for k in dir(thor_type_lib):
        v = getattr(thor_type_lib, k)
        if inspect.isclass(v) and issubclass(v, betterproto.Message):
            key = f'/types.{k}'
            result[key] = v
    return result


THORCHAIN_MESSAGES_MAP = register_thorchain_messages()


class NativeThorTx:
    def __init__(self, tx: Tx, hash: str = ''):
        self.tx = tx
        self.hash = hash

    @classmethod
    def from_bytes(cls, data: bytes):
        tx = Tx().parse(data)
        messages = []
        for msg in tx.body.messages:
            proto_type = THORCHAIN_MESSAGES_MAP.get(msg.type_url)
            messages.append(
                proto_type().parse(msg.value) if proto_type else msg
            )
        tx.body.messages = messages
        tx_hash = hashlib.sha256(data).hexdigest().upper()
        return cls(tx, tx_hash)

    @classmethod
    def from_base64(cls, data):
        if isinstance(data, str):
            data = data.encode()

        raw_data = base64.decodebytes(data)
        return cls.from_bytes(raw_data)

    @property
    def first_message(self):
        return self.messages[0] if self.messages else None

    @property
    def messages(self):
        return self.tx.body.messages


def thor_decode_amount_field(string: str):
    """ e.g. 114731984rune """
    amt, asset = '', ''
    still_numbers = True

    for symbol in string:
        if not str.isdigit(symbol):
            still_numbers = False
        if still_numbers:
            amt += symbol
        else:
            asset += symbol

    return (int(amt) if amt else 0), asset


def debase64(s: str):
    return base64.decodebytes(s.encode()).decode()


def block_events(block):
    try:
        return block['data']['value']['result_end_block']['events']
    except LookupError:
        return []


class DecodedEvent(typing.NamedTuple):
    type: str
    attributes: typing.Dict[str, str]


def thor_decode_event(e) -> DecodedEvent:
    decoded_attrs = {}
    for attr in e['attributes']:
        key = debase64(attr['key'])
        value = debase64(attr['value'])
        if key == 'amount':
            amount, asset = thor_decode_amount_field(value)
            value = amount, asset.upper()
        decoded_attrs[key] = value
    return DecodedEvent(e['type'], decoded_attrs)
