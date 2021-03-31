from services.dialog.picture.crypto_logo import convert_eth_address_to_case_checksum


def test_eth_addr():
    assert convert_eth_address_to_case_checksum(
        '0x9C33eaCc2F50E39940D3AfaF2c7B8246B681A374'.lower()) == '0x9C33eaCc2F50E39940D3AfaF2c7B8246B681A374'
    assert convert_eth_address_to_case_checksum(
        '0x0192e7b8C370a76237445aa653a727eCD6382677'.lower()) == '0x0192e7b8C370a76237445aa653a727eCD6382677'
    assert convert_eth_address_to_case_checksum(
        '0x668B189b56ae45Bf7D1f3100Fa6a2335f37479a4'.lower()) == '0x668B189b56ae45Bf7D1f3100Fa6a2335f37479a4'
