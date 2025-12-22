import asyncio
import logging
import random

from jobs.scanner.scan_cache import BlockScannerCached
from lib.constants import NATIVE_RUNE_SYMBOL
from lib.texts import sep
from lib.utils import safe_get
from models.asset import is_rune, Asset
from models.memo import THORMemo
from models.s_swap import StreamingSwap, AlertSwapStart
from notify.public.s_swap_notify import StreamingSwapStartTxNotifier
from tools.lib.lp_common import LpAppFramework


async def pick_random_ongoing_streaming_swap(app: LpAppFramework):
    s_swaps = await app.deps.thor_connector.query_raw('/thorchain/swaps/streaming')
    s_swaps = [StreamingSwap.model_validate(ss) for ss in s_swaps]
    if not s_swaps:
        raise RuntimeError("There is no ongoing streaming swaps!")

    print(f'{len(s_swaps) = }')
    s_swap = random.choice(s_swaps)
    print(s_swap)
    return s_swap


async def dbg_steaming_swap_start_pipeline(app: LpAppFramework):
    d = app.deps
    last_block = await d.last_block_cache.get_thor_block()
    d.block_scanner = BlockScannerCached(d, last_block=last_block - 1000)

    stream_swap_notifier = StreamingSwapStartTxNotifier(d)
    d.block_scanner.add_subscriber(stream_swap_notifier)
    stream_swap_notifier.add_subscriber(d.alert_presenter)

    await d.block_scanner.run()


async def dbg_quote(app: LpAppFramework):
    s_swap: StreamingSwap = await pick_random_ongoing_streaming_swap(app)
    tx_id = s_swap.tx_id
    tx = await app.deps.thor_connector.query_tx_details(tx_id)

    coin_in = safe_get(tx, 'tx', 'tx', 'coins', 0)

    print(tx)
    sep()
    print(coin_in)

    quote = await app.deps.thor_connector.query_swap_quote(
        from_asset=coin_in['asset'],
        to_asset='BTC.BTC',
        amount=coin_in['amount'],
        # refund_address=event.from_address,
        streaming_quantity=s_swap.quantity,
        streaming_interval=s_swap.interval,
        tolerance_bps=10000,  # MAX
        # affiliate='t' if event.memo.affiliates else '',  # does not matter for quote
        affiliate_bps=0,
        height=s_swap.last_height,  # for historical quotes
    )
    sep()
    print(quote)


FAILED_TO_QUOTE_TX = "0B2EEDCC08DF48999702784D31F8A4E10B48D3892D4AAE449E137B4BE197957B"


async def dbg_try_to_quote_specific_tx(app: LpAppFramework, tx_id):
    tx_details = await app.deps.thor_connector.query_tx_details(tx_id)

    coin_in = safe_get(tx_details, 'tx', 'tx', 'coins', 0)
    amount = int(coin_in['amount'])
    asset = coin_in['asset']
    memo = safe_get(tx_details, 'tx', 'tx', 'memo')
    memo = THORMemo.parse_memo(memo)

    print(f'Trying to quote for TX {tx_id}: {amount} {asset}')
    print(f'Memo: {memo}')

    quote = await app.deps.thor_connector.query_swap_quote(
        from_asset=asset,
        to_asset=memo.asset,
        amount=amount,
        # refund_address=event.from_address,
        streaming_quantity=memo.s_swap_quantity,
        streaming_interval=memo.s_swap_interval,
        tolerance_bps=10000,  # MAX
        # affiliate='t' if event.memo.affiliates else '',  # does not matter for quote
        affiliate_bps=0,
        # height=s_swap.last_height,  # for historical quotes
    )
    sep()
    print(quote)


async def dbg_try_to_quote_almost_naturally(app: LpAppFramework):
    notifier = StreamingSwapStartTxNotifier(app.deps)
    s_swap: StreamingSwap = await pick_random_ongoing_streaming_swap(app)

    details = await app.deps.thor_connector.query_tx_details(s_swap.tx_id)

    tx = safe_get(details, 'tx', 'tx')
    coin = safe_get(tx, 'coins', 0)

    memo_str = safe_get(tx, 'memo')
    memo = THORMemo.parse_memo(memo_str, no_raise=True)

    ph = await app.deps.pool_cache.get()

    if is_rune(memo.asset):
        out_asset_name = NATIVE_RUNE_SYMBOL
    else:
        out_asset_name = ph.pool_fuzzy_first(memo.asset, restore_type=True)
        if not out_asset_name:
            out_asset_name = memo.asset
            logging.error(f'{out_asset_name = }: asset not found in the pool list!')

    if not out_asset_name:
        logging.error(f'{memo.asset}: asset not found!')
        return None

    in_asset = coin['asset']
    in_amount = int(coin['amount'])

    if str(in_asset) == NATIVE_RUNE_SYMBOL:
        volume_usd = in_amount * ph.usd_per_rune
    else:
        in_pool_name = ph.pool_fuzzy_first(Asset(in_asset).native_pool_name)
        if not in_pool_name:
            logging.warning(f'{in_asset.native_pool_name}: pool if inbound asset not found!')
            return None

        in_pool_info = ph.find_pool(in_pool_name)
        volume_usd = in_amount * in_pool_info.usd_per_asset

    height = safe_get(details, 'consensus_height', 0)

    event = AlertSwapStart(
        from_address=tx['from_address'],
        destination_address=tx['to_address'],
        in_amount=int(coin['amount']),
        in_asset=str(coin['asset']),
        out_asset=out_asset_name,
        volume_usd=volume_usd,
        block_height=height,
        memo=memo,
        memo_str=memo_str,  # original memo
        tx_id=s_swap.tx_id,
        quantity=s_swap.quantity,
        interval=s_swap.interval,
    )

    event = await notifier.load_extra_tx_information(event)
    print(event)
    sep('quote')
    print(event.quote)


async def run():
    app = LpAppFramework()
    async with app():
        # await dbg_quote(app)
        # await dbg_steaming_swap_start_pipeline(app)
        # await dbg_try_to_quote_specific_tx(app, FAILED_TO_QUOTE_TX)
        await dbg_try_to_quote_almost_naturally(app)


if __name__ == '__main__':
    asyncio.run(run())
