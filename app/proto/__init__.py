import base64
import inspect
from typing import Optional

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
    def __init__(self, tx: Tx):
        self.tx = tx

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
        return cls(tx)

    @classmethod
    def from_base64(cls, data):
        if isinstance(data, str):
            data = data.encode()

        raw_data = base64.decodebytes(data)
        return cls.from_bytes(raw_data)

    @property
    def first_message(self):
        return self.tx.body.messages[0] if self.tx.body.messages else None
