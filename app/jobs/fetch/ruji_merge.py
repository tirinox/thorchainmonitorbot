from jobs.fetch.base import BaseFetcher
from lib.depcont import DepContainer
from lib.utils import a_result_cached
from models.ruji import MergeSystem, MergeContract


class RujiMergeStatsFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = deps.cfg.as_interval("rujira.merge.period", "10m")
        super().__init__(deps, sleep_period=sleep_period)
        self.deps = deps
        self.system = MergeSystem([
            MergeContract(deps.thor_connector, address)
            for address in MergeSystem.RUJI_MERGE_CONTRACTS
        ])

    async def fetch(self):
        for contract in self.system.contracts:
            contract.connector = self.deps.thor_connector
            await contract.load_config()
            await contract.load_status()

        prices = await self.get_prices_usd_from_gecko()
        self.system.set_prices(prices)

        return self.system

    @a_result_cached(ttl=120.0)
    async def get_prices_usd_from_gecko(self):
        url = "https://api.coingecko.com/api/v3/simple/price"
        coin_ids = {
            "LVN": "levana-protocol",
            "KUJI": "kujira",
            "FUZN": "fuzion",
            "WINK": "winkhub",
            "NSTK": "unstake"
        }
        params = {
            "ids": ",".join(coin_ids.values()),
            "vs_currencies": "usd"
        }

        async with self.deps.session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                prices = {coin: data.get(coin_ids[coin], {}).get("usd") for coin in coin_ids}

                # Check for missing prices and set defaults
                if not prices.get("NSTK"):
                    self.logger.warning(f"No NSTK price. Using last known hardcoded value")
                    prices["NSTK"] = 0.01253
                prices["RKUJI"] = prices["KUJI"]

                return prices
            else:
                raise Exception(f"Failed to fetch data. Status code: {response.status}")
