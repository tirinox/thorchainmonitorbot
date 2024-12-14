import base64
import hashlib

import bech32


def parse_thor_address(addr: bytes, prefix='thor') -> str:
    if isinstance(addr, bytes) and addr.startswith(prefix.encode('utf-8')):
        return addr.decode('utf-8')

    bits = list(addr)
    good_bits = bech32.convertbits(bits, 8, 5)
    return bech32.bech32_encode(prefix, good_bits)


def debase64(s: str) -> bytes:
    if not s:
        return b''
    b = s.encode()
    dec = base64.decodebytes(b)
    return dec


def pubkey_to_thor_address(pubkey: str, prefix='thor') -> str:
    pubkey = debase64(pubkey)
    s = hashlib.new("sha256", pubkey).digest()
    r = hashlib.new("ripemd160", s).digest()
    five_bit_r = bech32.convertbits(r, 8, 5)
    assert five_bit_r is not None, "Unsuccessful bech32.convertbits call"
    return bech32.bech32_encode(prefix, five_bit_r)


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
