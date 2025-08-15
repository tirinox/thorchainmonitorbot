import asyncio
import logging
from datetime import datetime

from jobs.fetch.pool_price import PoolFetcher
from jobs.price_recorder import PriceRecorder
from lib.constants import TCY_SYMBOL, THOR_BLOCK_TIME
from lib.date_utils import now_ts
from lib.money import pretty_dollar
from models.price import LastPriceHolder
from tools.lib.lp_common import LpAppFramework, ask_yes_no


async def fill_tcy_timeseries_task(app):
    pf: PoolFetcher = app.deps.pool_fetcher

    last_block = await app.deps.last_block_cache.get_thor_block()
    if not last_block:
        print("Last block not found. Exiting.")
        return

    price_recorder = PriceRecorder(app.deps.db)

    if ask_yes_no("Do you want to clear TCY timeseries?", default=False):
        await price_recorder.tcy_price_series.clear()

    all_keys = []
    async for block_no, pools in pf.cache.scan_all_keys():
        if TCY_SYMBOL in pools:
            all_keys.append(block_no)

    all_keys.sort()
    print(f"Found {len(all_keys)} blocks with TCY symbol. Min: {all_keys[0]}, Max: {all_keys[-1]}")

    if not ask_yes_no("Do you want to fill TCY timeseries?"):
        return

    for block_no in all_keys:
        pools = await pf.cache.get(block_no)
        if TCY_SYMBOL in pools:
            price_holder = LastPriceHolder().update_pools(pools)

            tcy_price = price_holder.get_asset_price_in_usd(TCY_SYMBOL)

            ts = now_ts() - (last_block - block_no) * THOR_BLOCK_TIME
            readable_date = datetime.fromtimestamp(ts).strftime('%H:%M %d.%m.%Y')

            print(f"Block: {block_no}, date: {readable_date} TCY price: {pretty_dollar(tcy_price)}")

            await price_recorder.tcy_price_series.add_ts(ts, price=tcy_price)


async def main():
    app = LpAppFramework(log_level=logging.DEBUG)
    async with app(brief=True):
        await fill_tcy_timeseries_task(app)


if __name__ == '__main__':
    asyncio.run(main())
