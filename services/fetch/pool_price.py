from services.config import Config
from services.db import DB
from services.fetch.base import BaseFetcher, INotified
from services.fetch.fair_price import fair_rune_price
from services.fetch.node_ip_manager import ThorNodeAddressManager
from services.models.pool_info import PoolInfo
from services.models.price import LastPrice
from services.models.time_series import PriceTimeSeries, BUSD_SYMBOL, RUNE_SYMBOL, RUNE_SYMBOL_DET


class PoolPriceFetcher(BaseFetcher):
    def __init__(self, cfg: Config, db: DB, thor_man: ThorNodeAddressManager = ThorNodeAddressManager.shared(),
                 session=None, delegate: INotified = None, holder: LastPrice = None):
        super().__init__(cfg, db, session, delegate=delegate, sleep_period=cfg.price.fetch_period)
        self.thor_man = thor_man
        self.session = session
        self.price_holder = holder

    async def fetch(self):
        price = await self.get_price_in_rune(BUSD_SYMBOL)
        self.logger.info(f'fresh rune price is ${self.price_holder.rune_price_in_usd:.3f}')

        if price > 0:
            self.price_holder.rune_price_in_usd = price
            pts = PriceTimeSeries(RUNE_SYMBOL, self.db)
            await pts.add(price=price)

            pts_det = PriceTimeSeries(RUNE_SYMBOL_DET, self.db)
            fair_price = await fair_rune_price()
            await pts_det.add(price=fair_price.fair_price)

            return price, fair_price

    async def fetch_pool_data_historic(self, asset, height=0) -> PoolInfo:
        if asset == RUNE_SYMBOL:
            return PoolInfo.dummy()

        base_url = await self.thor_man.select_node_url()

        url = f"{base_url}/thorchain/pool/{asset}?height={height}"

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

        url = f"{base_url}/thorchain/pools"
        self.logger.info(f"loading pool data from {url}")
        async with self.session.get(url) as resp:
            pools_info = await resp.json()
            return {
                pool['asset']: PoolInfo.from_dict(pool) for pool in pools_info
            }

    async def get_prices_of(self, asset_list):
        pool_dict = await self.get_current_pool_data_full()
        return {
            asset: pool for asset, pool in pool_dict.items() if pool in asset_list
        }
