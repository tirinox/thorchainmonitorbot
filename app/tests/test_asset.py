from services.lib.money import Asset, short_address


def test_asset1():
    a1 = Asset('ETH.XRUNE-0X69FA0FEE221AD11012BAB0FDB45D444D3D2CE71C')
    assert a1.chain == 'ETH'
    assert a1.name == 'XRUNE'
    assert a1.tag == '0X69FA0FEE221AD11012BAB0FDB45D444D3D2CE71C'
    assert str(a1) == 'ETH.XRUNE-0X69FA0FEE221AD11012BAB0FDB45D444D3D2CE71C'

    assert Asset('ETH.XRUNE-0X69FA0FEE221AD11012BAB0FDB45D444D3D2CE71C') == \
           Asset.from_string('ETH.XRUNE-0X69FA0FEE221AD11012BAB0FDB45D444D3D2CE71C')

    ea = Asset.from_string('')
    assert str(ea) == ''

    a2 = Asset.from_string('ETH.DODO-0X43DFC4159D86F3A37A5A4B3D4580B888AD7D4DDD')
    a2s = Asset.from_string('eTh.dODo-0X43dFC4159D86F3A37A5A4b3d4580B888AD7D4DDD')
    assert a2 == a2s
    assert a2s.chain_id == 'ETH'
    assert a2s.name == 'DODO'
    assert a2s.tag == '0X43DFC4159D86F3A37A5A4B3D4580B888AD7D4DDD'

    assert a2s.pretty_str == 'ETH.DODO-0X43DF'

    a3 = Asset('BNB.BNB')
    assert a3.chain == 'BNB'
    assert a3.name == 'BNB'
    assert a3.tag == ''
    assert str(a3) == 'BNB.BNB'
    assert a3.pretty_str == 'BNB.BNB'


def test_synth_asset_name():
    a1 = Asset("BNB/BTCB-1DE")
    assert a1.is_synth
    assert a1.name == 'BTCB'
    assert a1.tag == '1DE'
    assert a1.chain == 'BNB'
    assert a1.pretty_str == '💊BNB/BTCB-1DE'

    a2 = Asset("btc/btc")
    assert a2.is_synth
    assert a2.name == 'BTC'
    assert a2.chain == 'BTC'

    a3 = Asset.from_string("BTC/btc")
    assert a3 == a2
    assert a3.pretty_str == '💊BTC/BTC'

    a4 = Asset('ETH/USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48')
    assert a4.tag == '0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48'
    assert a4.chain == 'ETH'
    assert a4.name == 'USDC'
    assert a4.pretty_str == '💊ETH/USDC-0XA0B8'

    a5 = Asset('eth/yfi-0x0bc529c00c6401aef6d220be8c6ea1667f6ad93e')
    assert a5.tag == '0X0BC529C00C6401AEF6D220BE8C6EA1667F6AD93E'
    assert a5.chain == 'ETH'
    assert a5.name == 'YFI'
    assert a5.pretty_str == '💊ETH/YFI-0X0BC5'


def test_convert_synth():
    p1 = Asset.to_L1_pool_name('ETH/USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48')
    assert p1 == 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48'

    assert Asset.to_L1_pool_name('ETH.ETH') == 'ETH.ETH'
    assert Asset.to_L1_pool_name('BTC/BTC') == 'BTC.BTC'


def test_short_asset():
    assert short_address('thor1xd4j3gk9frpxh8r22runntnqy34lwzrdkazldh') == 'thor1xd...zldh'
    assert short_address('thor1xd4j3gk9frpxh8r22runntnqy34lwzrdkazldh', 0) == 'zldh'
    assert short_address('thor1xd4j3gk9frpxh8r22runntnqy34lwzrdkazldh', begin=5, end=0) == 'thor1'
