from api.midgard.name_service import NameMap
from comm.localization.twitter_eng import TwitterEnglishLocalization
from lib.config import Config
from models.memo import ActionType, THORMemo
from models.s_swap import AlertSwapStart, StreamingSwap
from models.tx import EventLargeTransaction, SUCCESS, ThorAction, ThorCoin, ThorMetaSwap, ThorSubTx


TX_ID = 'ABCDEF123456'
THOR_ADDR = 'thor1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq6c6n30'
BTC_ADDR = 'bc1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqe36w8h'


def _make_localization(threshold_usd: float) -> TwitterEnglishLocalization:
    return TwitterEnglishLocalization(Config(data={
        'twitter': {
            'max_length': 280,
        },
        'tx': {
            'swap': {
                'twitter': {
                    'remove_links_below_usd': threshold_usd,
                },
            },
        },
    }))


def _make_swap_started(volume_usd: float) -> AlertSwapStart:
    return AlertSwapStart(
        tx_id=TX_ID,
        from_address=THOR_ADDR,
        destination_address=BTC_ADDR,
        in_amount=100_000000,
        in_asset='THOR.RUNE',
        out_asset='BTC.BTC',
        volume_usd=volume_usd,
        block_height=1,
        memo=THORMemo(ActionType.SWAP),
        memo_str='',
        quantity=3,
        interval=10,
    )


def _make_swap_finished(volume_usd: float) -> EventLargeTransaction:
    tx = ThorAction(
        date_timestamp=0,
        height=1,
        status=SUCCESS,
        type=ActionType.SWAP.value,
        pools=['BTC.BTC'],
        in_tx=[ThorSubTx(
            address=THOR_ADDR,
            coins=[ThorCoin(amount=100_000000, asset='THOR.RUNE')],
            tx_id=TX_ID,
        )],
        out_tx=[ThorSubTx(
            address=BTC_ADDR,
            coins=[ThorCoin(amount=10_000, asset='BTC.BTC')],
            tx_id='FEDCBA654321',
        )],
        meta_swap=ThorMetaSwap(
            liquidity_fee=0,
            network_fees=[],
            trade_slip=0,
            trade_target=0,
            streaming=StreamingSwap(tx_id=TX_ID, quantity=3, interval=10),
        ),
    )
    usd_per_rune = 2.0
    tx.full_volume_in_rune = volume_usd / usd_per_rune
    return EventLargeTransaction(transaction=tx, usd_per_rune=usd_per_rune)


def test_small_streaming_swap_started_hides_urls():
    text = _make_localization(1_000).notification_text_streaming_swap_started(
        _make_swap_started(999),
        NameMap.empty(),
    )

    assert 'Track Tx:' not in text
    assert 'Runescan:' not in text


def test_large_streaming_swap_started_keeps_urls():
    text = _make_localization(1_000).notification_text_streaming_swap_started(
        _make_swap_started(1_000),
        NameMap.empty(),
    )

    assert 'Track Tx:' in text
    assert 'Runescan:' in text


def test_small_streaming_swap_finished_hides_urls():
    text = _make_localization(1_000).notification_text_large_single_tx(
        _make_swap_finished(999),
        NameMap.empty(),
    )

    assert 'Runescan:' not in text


def test_large_streaming_swap_finished_keeps_urls():
    text = _make_localization(1_000).notification_text_large_single_tx(
        _make_swap_finished(1_000),
        NameMap.empty(),
    )

    assert 'Runescan:' in text


