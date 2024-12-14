import bech32


def parse_thor_address(addr: bytes, prefix='thor') -> str:
    if isinstance(addr, bytes) and addr.startswith(prefix.encode('utf-8')):
        return addr.decode('utf-8')

    good_bits = bech32.convertbits(list(addr), 8, 5, False)
    return bech32.bech32_encode(prefix, good_bits)


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
