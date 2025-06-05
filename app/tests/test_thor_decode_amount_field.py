import pytest

from jobs.scanner.util import thor_decode_amount_field


@pytest.mark.parametrize("input_str, expected", [
    ("114731984 rune", (114731984, "RUNE")),
    ("BSC.BNB-0x33434 900514", (900514, "BSC.BNB-0X33434")),
    ("ETH-LINK-0xaabb553353 23328899", (23328899, "ETH-LINK-0xAABB553353")),
    ("ETH-LINK-0xaabb553353 0", (0, "ETH-LINK-0xAABB553353")),
    ("114731984rune", (114731984, "RUNE")),
    ("0rune", (0, "RUNE")),
    ("98765btc", (98765, "BTC")),
    ("BTC 123456", (123456, "BTC")),
    ("BTC~BTC 0", (0, "BTC~BTC")),
])
def test_valid_cases(input_str, expected):
    assert thor_decode_amount_field(input_str) == expected


@pytest.mark.parametrize("invalid_input", [
    "nonsense",
    "12345 ",  # asset missing
    " rune",  # amount missing
    "12 34 56",  # multiple spaces
    "",  # empty string
])
def test_invalid_cases(invalid_input):
    with pytest.raises(ValueError):
        thor_decode_amount_field(invalid_input)
