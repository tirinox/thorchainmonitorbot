import pytest

from lib.money import short_address
from models.asset import Asset
from models.asset import is_ambiguous_asset, AssetKind


@pytest.mark.parametrize("asset_string, expected_chain, expected_name, expected_tag, expected_str", [
    ('ETH.XRUNE-0X69FA0FEE221AD11012BAB0FDB45D444D3D2CE71C', 'ETH', 'XRUNE', '0X69FA0FEE221AD11012BAB0FDB45D444D3D2CE71C', 'ETH.XRUNE-0X69FA0FEE221AD11012BAB0FDB45D444D3D2CE71C'),
    ('ETH.DODO-0X43DFC4159D86F3A37A5A4B3D4580B888AD7D4DDD', 'ETH', 'DODO', '0X43DFC4159D86F3A37A5A4B3D4580B888AD7D4DDD', 'ETH.DODO-0X43DFC4159D86F3A37A5A4B3D4580B888AD7D4DDD'),
    ('BNB.BSC', 'BNB', 'BSC', '', 'BNB.BSC'),
    ('XRP/FLR', 'XRP', 'FLR', '', 'XRP/FLR'),
    ('XRP~FLR', 'XRP', 'FLR', '', 'XRP~FLR'),
])
def test_asset1(asset_string, expected_chain, expected_name, expected_tag, expected_str):
    asset = Asset(asset_string)
    assert asset.chain == expected_chain
    assert asset.name == expected_name
    assert asset.tag == expected_tag
    assert str(asset) == expected_str
    assert asset == Asset.from_string(asset_string)


@pytest.mark.parametrize("asset_string, peculiarities, expected_name, expected_tag, expected_chain, expected_pretty_str", [
    ("eth-yfi-0x0bc529c00c6401aef6d220be8c6ea1667f6ad93e", "secured", "YFI", "0X0BC529C00C6401AEF6D220BE8C6EA1667F6AD93E",
     "ETH", "secured ETH-YFI"),
    ("eth~yfi-0x0bc529c00c6401aef6d220be8c6ea1667f6ad93e", "trade", "YFI", "0X0BC529C00C6401AEF6D220BE8C6EA1667F6AD93E",
     "ETH", "trade ETH~YFI"),
    ("eth.yfi-0x0bc529c00c6401aef6d220be8c6ea1667f6ad93e", "", "YFI", "0X0BC529C00C6401AEF6D220BE8C6EA1667F6AD93E",
     "ETH", "ETH.YFI"),
    ("ETH/USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48", "synth", "USDC",
     "0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48", "ETH", "synth ETH/USDC"),
    ("BNB/BTCB-1DE", "synth", "BTCB", "1DE", "BNB", "synth BNB/BTCB"),
    ("BSC~BNB-0x123", "trade", "BNB", "0X123", "BSC", "trade BSC~BNB"),
    ("btc/btc", "synth", "BTC", "", "BTC", "synth BTC"),
    ("BTC/btc", "synth", "BTC", "", "BTC", "synth BTC"),
])
def test_synth_asset_name(asset_string, peculiarities, expected_name, expected_tag, expected_chain, expected_pretty_str):
    asset = Asset(asset_string)
    peculiarities = peculiarities.split(',') if isinstance(peculiarities, str) else peculiarities
    assert asset.is_synth == ('synth' in peculiarities)
    assert asset.is_trade == ('trade' in peculiarities)
    assert asset.is_secured == ('secured' in peculiarities)
    assert asset.name == expected_name
    assert asset.tag == expected_tag
    assert asset.chain == expected_chain
    assert asset.pretty_str == expected_pretty_str


def test_restore_asset():
    assert AssetKind.restore_asset_type('BSC~BNB', 'XRP.XRP') == 'XRP~XRP'
    assert AssetKind.restore_asset_type('BSC/BNB', 'XRP.XRP') == 'XRP/XRP'
    assert AssetKind.restore_asset_type('BSC~BNB', 'XRP.XRP') == 'XRP~XRP'
    assert AssetKind.restore_asset_type('XRP.XRP', 'XRP.XRP') == 'XRP.XRP'
    assert AssetKind.restore_asset_type('ETH/USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48', 'XRP.XRP') == 'XRP/XRP'


def test_recognize_kind():
    assert AssetKind.recognize('XRP') == AssetKind.UNKNOWN
    assert AssetKind.recognize('XRP.XRP') == AssetKind.NATIVE
    assert AssetKind.recognize('ETH/ETH') == AssetKind.SYNTH
    assert AssetKind.recognize('ETH~ETH') == AssetKind.TRADE
    assert AssetKind.recognize('ETH-ETH') == AssetKind.SECURED

    assert AssetKind.recognize('ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48') == AssetKind.NATIVE
    assert AssetKind.recognize('ETH-USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48') == AssetKind.SECURED
    assert AssetKind.recognize('ETH/USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48') == AssetKind.SYNTH
    assert AssetKind.recognize('ETH~USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48') == AssetKind.TRADE


def test_convert_synth():
    p1 = Asset.to_L1_pool_name('ETH/USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48')
    assert p1 == 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48'

    assert Asset.to_L1_pool_name('ETH.ETH') == 'ETH.ETH'
    assert Asset.to_L1_pool_name('BTC/BTC') == 'BTC.BTC'


def test_short_asset():
    assert short_address('thor1xd4j3gk9frpxh8r22runntnqy34lwzrdkazldh') == 'thor1xd...zldh'
    assert short_address('thor1xd4j3gk9frpxh8r22runntnqy34lwzrdkazldh', 0) == 'zldh'
    assert short_address('thor1xd4j3gk9frpxh8r22runntnqy34lwzrdkazldh', begin=5, end=0) == 'thor1'


def test_gas_asset():
    assert Asset.from_string('ETH.ETH').is_gas_asset
    assert Asset.from_string('AVAX.AVAX').is_gas_asset
    assert Asset.from_string('BTC.BTC').is_gas_asset
    assert Asset.from_string('THOR.RUNE').is_gas_asset
    assert Asset.from_string('GAIA.ATOM').is_gas_asset
    assert Asset.from_string('BSC.BNB').is_gas_asset

    assert not Asset.from_string('BSC.BUSD').is_gas_asset
    assert not Asset.from_string('BSC.BNB-0x123').is_gas_asset
    assert not Asset.from_string('ETH.USDT-0x123').is_gas_asset


def test_ambiguous_name():
    assert is_ambiguous_asset('GIAI.ATOM', [])
    assert not is_ambiguous_asset('ETH.ETH', [])
    assert not is_ambiguous_asset('BTC.BTC', [])
    assert is_ambiguous_asset('THOR.BTC', [])
    assert is_ambiguous_asset('ETH.ETH', ['ETH.ETH', 'ARB.ETH'])
    assert not is_ambiguous_asset('ETH.ETH', ['ETH.ETH', 'LTC.LTC', 'DOGE.DOGE'])

    assert not is_ambiguous_asset('ETH~ETH')
    assert not is_ambiguous_asset('BTC~BTC')


@pytest.mark.parametrize('asset_name, chain', [
    ('ETH.ETH', 'ETH'),
    ('BTC.BTC', 'BTC'),
    ('LTC.LTC', 'LTC'),
    ('AVAX.AVAX', 'AVAX'),
    ('DOGE.DOGE', 'DOGE'),
    ('GAIA.ATOM', 'GAIA'),
    ('BSC.BNB', 'BSC'),
    ('XRP.XRP', 'XRP')
])
def test_l1_asset_vs_gas_asset(asset_name, chain):
    # assert Chains.l1_asset(chain) == asset_name
    assert str(Asset.gas_asset_from_chain(chain)) == asset_name
