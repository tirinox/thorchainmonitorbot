from services.lib.money import Asset


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
    assert a2s.chain == 'ETH'
    assert a2s.name == 'DODO'
    assert a2s.tag == '0X43DFC4159D86F3A37A5A4B3D4580B888AD7D4DDD'

    assert a2s.short_str == 'ETH.DODO-0X43DF'

    a3 = Asset('BNB.BNB')
    assert a3.chain == 'BNB'
    assert a3.name == 'BNB'
    assert a3.tag == ''
    assert str(a3) == 'BNB.BNB'
    assert a3.short_str == 'BNB.BNB'
