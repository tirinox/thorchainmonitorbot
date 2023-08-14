import base64
import hashlib
import inspect
import typing

import bech32
import betterproto

import proto.types as thor_type_lib
from proto.cosmos.tx.v1beta1 import Tx


def parse_thor_address(addr: bytes, prefix='thor') -> str:
    if isinstance(addr, bytes) and addr.startswith(prefix.encode('utf-8')):
        return addr.decode('utf-8')

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
    def __init__(self, tx: Tx, tx_hash: str = ''):
        self.tx = tx
        self.hash = tx_hash

    def __repr__(self) -> str:
        return repr(self.tx)

    def __str__(self):
        return str(self.tx)

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

    return (int(amt) if amt else 0), asset.strip().upper()


def debase64(s: str):
    if not s:
        return b''
    return base64.decodebytes(s.encode()).decode()


def block_events(block):
    try:
        return block['data']['value']['result_end_block']['events']
    except LookupError:
        return []


class DecodedEvent(typing.NamedTuple):
    type: str
    attributes: typing.Dict[str, str]

    @classmethod
    def from_dict(cls, d):
        return cls(
            type=d['type'],
            attributes={attr['key']: attr.get('value') for attr in d['attributes']}
        )

    @property
    def to_dict(self):
        return {
            'type': self.type,
            'attributes': self.attributes
        }


def thor_decode_event(e) -> DecodedEvent:
    decoded_attrs = {}
    for attr in e['attributes']:
        key = debase64(attr.get('key'))
        value = debase64(attr.get('value'))
        decoded_attrs[key] = value
        if key == 'amount' or key == 'coin':
            decoded_attrs['amount'], decoded_attrs['asset'] = thor_decode_amount_field(value)

    return DecodedEvent(e.get('type', ''), decoded_attrs)
