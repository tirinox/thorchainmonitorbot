import pytest

from models.memo import THORMemo
from models.pool_info import PoolInfo
from models.price import PriceHolder
from models.s_swap import AlertSwapStart

USDC = 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48'


@pytest.fixture
def ph():
    ph = PriceHolder()
    ph.usd_per_rune = 2.0
    ph.pool_info_map = {
        'BTC.BTC': PoolInfo('BTC.BTC', balance_asset=500 * 10 ** 8, balance_rune=20_000_000 * 10 ** 8,
                            pool_units=1, status=PoolInfo.AVAILABLE),
        'ETH.ETH': PoolInfo('ETH.ETH', balance_asset=3000 * 10 ** 8, balance_rune=5_000_000 * 10 ** 8,
                            pool_units=1, status=PoolInfo.AVAILABLE),
        USDC: PoolInfo(USDC, balance_asset=4_000_000 * 10 ** 8, balance_rune=2_000_000 * 10 ** 8,
                       pool_units=1, status=PoolInfo.AVAILABLE),
    }
    return ph


@pytest.mark.parametrize('in_asset, out_asset, expected', [
    ('BTC.BTC', 'ETH.ETH', 'ETH.ETH'),  # double swap: the shallower pool
    ('ETH.ETH', 'BTC.BTC', 'ETH.ETH'),
    ('BTC~BTC', 'ETH-USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48', USDC),  # trade -> secured
    ('ETH/ETH', 'BTC.BTC', 'ETH.ETH'),  # synth
    ('THOR.RUNE', 'BTC.BTC', 'BTC.BTC'),  # single swap from RUNE
    ('BTC.BTC', 'THOR.RUNE', 'BTC.BTC'),  # single swap to RUNE
    ('DOGE.DOGE', 'BTC.BTC', 'BTC.BTC'),  # unknown pool is skipped
    ('DOGE.DOGE', 'THOR.RUNE', None),
])
def test_shallowest_pool_on_route(ph, in_asset, out_asset, expected):
    pool = ph.shallowest_pool_on_route(in_asset, out_asset)
    assert (pool.asset if pool else None) == expected


def _swap_start(volume_usd, pool_depth_usd):
    return AlertSwapStart(
        tx_id='TX', from_address='addr', destination_address='dest', in_amount=10 ** 8,
        in_asset='BTC.BTC', out_asset='ETH.ETH', volume_usd=volume_usd, block_height=1,
        memo=THORMemo.parse_memo('=:ETH.ETH:dest'), memo_str='=:ETH.ETH:dest',
        pool_depth_usd=pool_depth_usd,
    )


def test_volume_to_pool_depth_percent(ph):
    eth_depth = ph.find_pool('ETH.ETH').usd_depth(ph.usd_per_rune)
    assert eth_depth == pytest.approx(20_000_000.0)  # 2 sides * 5M RUNE * $2
    assert _swap_start(1_000_000, eth_depth).volume_to_pool_depth_percent == pytest.approx(5.0)
    assert _swap_start(1_000_000, 0.0).volume_to_pool_depth_percent == 0.0
