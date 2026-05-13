from types import SimpleNamespace

from api.midgard.name_service import NameMap
from comm.localization import twitter_eng as twitter_eng_module
from comm.localization.twitter_eng import TwitterEnglishLocalization
from lib.config import Config
from models.memo import ActionType, THORMemo
from models.runepool import AlertRunePoolAction
from models.s_swap import AlertSwapStart, StreamingSwap
from models.trade_acc import AlertTradeAccountAction
from models.transfer import NativeTokenTransfer
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


def _set_post_urls_enabled(monkeypatch, enabled: bool):
    monkeypatch.setattr(twitter_eng_module, 'TWITTER_POST_URLS_ENABLED', enabled)


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


def test_small_streaming_swap_started_hides_urls(monkeypatch):
    _set_post_urls_enabled(monkeypatch, True)
    text = _make_localization(1_000).notification_text_streaming_swap_started(
        _make_swap_started(999),
        NameMap.empty(),
    )

    assert 'Track Tx:' not in text
    assert 'Runescan:' not in text


def test_large_streaming_swap_started_keeps_urls(monkeypatch):
    _set_post_urls_enabled(monkeypatch, True)
    text = _make_localization(1_000).notification_text_streaming_swap_started(
        _make_swap_started(1_000),
        NameMap.empty(),
    )

    assert 'Track Tx:' in text
    assert 'Runescan:' in text


def test_small_streaming_swap_finished_hides_urls(monkeypatch):
    _set_post_urls_enabled(monkeypatch, True)
    text = _make_localization(1_000).notification_text_large_single_tx(
        _make_swap_finished(999),
        NameMap.empty(),
    )

    assert 'Runescan:' not in text


def test_large_streaming_swap_finished_keeps_urls(monkeypatch):
    _set_post_urls_enabled(monkeypatch, True)
    text = _make_localization(1_000).notification_text_large_single_tx(
        _make_swap_finished(1_000),
        NameMap.empty(),
    )

    assert 'Runescan:' in text


def test_price_update_has_no_urls_by_default():
    loc = _make_localization(0)
    text = loc.notification_text_price_update(SimpleNamespace(
        is_ath=True,
        market_info=SimpleNamespace(pool_rune_price=1.234),
        btc_pool_rune_price=0.00001234,
    ))

    assert 'http' not in text
    assert 'CoinGecko' not in text
    assert 'Start trading now' not in text


def test_price_update_restores_urls_when_enabled(monkeypatch):
    _set_post_urls_enabled(monkeypatch, True)
    loc = _make_localization(0)
    text = loc.notification_text_price_update(SimpleNamespace(
        is_ath=True,
        market_info=SimpleNamespace(pool_rune_price=1.234),
        btc_pool_rune_price=0.00001234,
    ))

    assert 'CoinGecko' in text
    assert 'Start trading now' in text
    assert 'http' in text


def test_pool_churn_has_no_urls_by_default():
    loc = _make_localization(0)
    text = loc.notification_text_pool_churn(SimpleNamespace(
        pools_added=[('BTC.BTC', 'staged', 'available')],
        pools_removed=[],
        pools_changed=[],
    ))

    assert 'http' not in text
    assert 'thorchain.net/pools' not in text


def test_pool_churn_restores_url_when_enabled(monkeypatch):
    _set_post_urls_enabled(monkeypatch, True)
    loc = _make_localization(0)
    text = loc.notification_text_pool_churn(SimpleNamespace(
        pools_added=[('BTC.BTC', 'staged', 'available')],
        pools_removed=[],
        pools_changed=[],
    ))

    assert 'thorchain.net/pools' in text


def test_public_rune_transfer_has_no_tx_url_by_default():
    loc = _make_localization(0)
    text = loc.notification_text_rune_transfer_public(
        NativeTokenTransfer(
            from_addr=THOR_ADDR,
            to_addr=BTC_ADDR,
            block=1,
            tx_hash=TX_ID,
            amount=123.0,
            usd_per_asset=2.0,
            asset='THOR.RUNE',
            comment='transfer',
        ),
        NameMap.empty(),
    )

    assert 'http' not in text
    assert 'TX:' not in text


def test_public_rune_transfer_restores_tx_url_when_enabled(monkeypatch):
    _set_post_urls_enabled(monkeypatch, True)
    loc = _make_localization(0)
    text = loc.notification_text_rune_transfer_public(
        NativeTokenTransfer(
            from_addr=THOR_ADDR,
            to_addr=BTC_ADDR,
            block=1,
            tx_hash=TX_ID,
            amount=123.0,
            usd_per_asset=2.0,
            asset='THOR.RUNE',
            comment='transfer',
        ),
        NameMap.empty(),
    )

    assert 'TX:' in text
    assert 'http' in text


def test_trade_account_move_has_no_tx_url_by_default():
    loc = _make_localization(0)
    text = loc.notification_text_trade_account_move(
        AlertTradeAccountAction(
            tx_hash=TX_ID,
            actor=THOR_ADDR,
            destination_address=BTC_ADDR,
            amount=42.0,
            usd_amount=84.0,
            asset='BTC.BTC',
            is_deposit=True,
            chain='BTC',
        ),
        NameMap.empty(),
    )

    assert 'http' not in text
    assert 'TX:' not in text


def test_trade_account_move_restores_tx_url_when_enabled(monkeypatch):
    _set_post_urls_enabled(monkeypatch, True)
    loc = _make_localization(0)
    text = loc.notification_text_trade_account_move(
        AlertTradeAccountAction(
            tx_hash=TX_ID,
            actor=THOR_ADDR,
            destination_address=BTC_ADDR,
            amount=42.0,
            usd_amount=84.0,
            asset='BTC.BTC',
            is_deposit=True,
            chain='BTC',
        ),
        NameMap.empty(),
    )

    assert 'TX:' in text
    assert 'http' in text


def test_runepool_action_has_no_tx_url_by_default():
    loc = _make_localization(0)
    text = loc.notification_runepool_action(
        AlertRunePoolAction(
            tx_hash=TX_ID,
            actor=THOR_ADDR,
            destination_address=BTC_ADDR,
            amount=50.0,
            usd_amount=100.0,
            is_deposit=True,
            height=1,
            memo=THORMemo(ActionType.RUNEPOOL_ADD),
        ),
        NameMap.empty(),
    )

    assert 'http' not in text
    assert 'TX:' not in text


def test_runepool_action_restores_tx_url_when_enabled(monkeypatch):
    _set_post_urls_enabled(monkeypatch, True)
    loc = _make_localization(0)
    text = loc.notification_runepool_action(
        AlertRunePoolAction(
            tx_hash=TX_ID,
            actor=THOR_ADDR,
            destination_address=BTC_ADDR,
            amount=50.0,
            usd_amount=100.0,
            is_deposit=True,
            height=1,
            memo=THORMemo(ActionType.RUNEPOOL_ADD),
        ),
        NameMap.empty(),
    )

    assert 'TX:' in text
    assert 'http' in text


def test_rujira_merge_stats_has_no_url_by_default():
    text = _make_localization(0).notification_rujira_merge_stats(SimpleNamespace())

    assert text == 'RUJIRA Merge stats $RUJI'
    assert 'http' not in text


def test_rujira_merge_stats_restores_url_when_enabled(monkeypatch):
    _set_post_urls_enabled(monkeypatch, True)
    text = _make_localization(0).notification_rujira_merge_stats(SimpleNamespace())

    assert 'RUJIRA Merge stats $RUJI' in text
    assert 'https://rujira.network/merge/' in text


