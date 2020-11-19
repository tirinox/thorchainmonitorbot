from services.lib.config import Config
from services.lib.db import DB
from services.fetch.base import BaseFetcher, INotified
from services.fetch.fair_price import fair_rune_price
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.models.pool_info import PoolInfo
from services.models.price import LastPriceHolder
from services.models.time_series import PriceTimeSeries, BUSD_SYMBOL, RUNE_SYMBOL, RUNE_SYMBOL_DET
from services.lib.datetime import parse_timespan_to_seconds


class PoolPriceFetcher(BaseFetcher):
    def __init__(self, cfg: Config, db: DB, thor_man: ThorNodeAddressManager = ThorNodeAddressManager.shared(),
                 session=None, delegate: INotified = None, holder: LastPriceHolder = None):
        period = parse_timespan_to_seconds(cfg.price.fetch_period)
        super().__init__(cfg, db, session, delegate=delegate, sleep_period=period)
        self.thor_man = thor_man
        self.session = session
        self.price_holder = holder

    @staticmethod
    def historic_url(base_url, asset, height):
        return f"{base_url}/thorchain/pool/{asset}?height={height}"

    @staticmethod
    def full_pools_url(base_url):
        return f"{base_url}/thorchain/pools"

    async def fetch(self):
        await self.get_current_pool_data_full()
        price = self.price_holder.rune_price_in_usd
        self.logger.info(f'fresh rune price is ${price:.3f}')

        if price > 0:
            self.price_holder.rune_price_in_usd = price
            pts = PriceTimeSeries(RUNE_SYMBOL, self.db)
            await pts.add(price=price)

            pts_det = PriceTimeSeries(RUNE_SYMBOL_DET, self.db)
            fair_price = await fair_rune_price()
            await pts_det.add(price=fair_price.fair_price)
            fair_price.real_rune_price = price
            return fair_price
        else:
            self.logger.warning(f'really ${price:.3f}? that is odd!')

    async def fetch_pool_data_historic(self, asset, height=0) -> PoolInfo:
        if asset == RUNE_SYMBOL:
            return PoolInfo.dummy()

        base_url = await self.thor_man.select_node_url()
        url = self.historic_url(base_url, asset, height)

        async with self.session.get(url) as resp:
            j = await resp.json()
            return PoolInfo.from_dict(j)

    async def get_price_in_rune(self, asset, height=0):
        if asset == RUNE_SYMBOL:
            return 1.0
        asset_pool = await self.fetch_pool_data_historic(asset, height)
        asset_per_rune = asset_pool.balance_asset / asset_pool.balance_rune
        return asset_per_rune

    async def get_historical_price(self, asset, height=0):
        dollar_per_rune = await self.get_price_in_rune(BUSD_SYMBOL, height)
        asset_per_rune = await self.get_price_in_rune(asset, height)

        asset_price_in_usd = dollar_per_rune / asset_per_rune

        return dollar_per_rune, asset_price_in_usd

    async def get_current_pool_data_full(self):
        base_url = await self.thor_man.select_node_url()
        url = self.full_pools_url(base_url)

        self.logger.info(f"loading pool data from {url}")

        async with self.session.get(url) as resp:
            pools_info = await resp.json()
            results = {
                pool['asset']: PoolInfo.from_dict(pool) for pool in pools_info
            }
            if results and self.price_holder is not None:
                self.price_holder.pool_info_map = results
                self.price_holder.update()
            return results

    async def get_prices_of(self, asset_list):
        pool_dict = await self.get_current_pool_data_full()
        return {
            asset: pool for asset, pool in pool_dict.items() if pool in asset_list
        }
