import asyncio
from contextlib import suppress
from typing import NamedTuple, Dict

from services.lib.constants import RUNE_IDEAL_SUPPLY, RUNE_SUPPLY_AFTER_SWITCH, thor_to_float, RUNE_DENOM, \
    RUBE_BURNT_ADR_12
from services.lib.utils import WithLogger


class ThorRealms:
    RESERVES = 'Reserve'
    STANDBY_RESERVES = '.'

    BONDED = 'Bonded'
    BONDED_NODE = 'Bonded (node)'
    LIQ_POOL = 'Pooled'
    RUNEPOOL = 'RUNEPool'
    POL = 'Protocol owned liquidity'
    CIRCULATING = 'Circulating'

    CEX = 'CEX'
    BURNED = 'Burned'
    MINTED = 'Minted'
    TREASURY = 'Treasury'
    MAYA_POOL = 'Maya'

    KILLED = 'Killed switched'


THOR_ADDRESS_DICT = {
    # Reserves:
    'thor1dheycdevq39qlkxs2a6wuuzyn4aqxhve4qxtxt': (ThorRealms.RESERVES, ThorRealms.RESERVES),
    'thor1lj62pg6ryxv2htekqx04nv7wd3g98qf9gfvamy': (ThorRealms.STANDBY_RESERVES, ThorRealms.STANDBY_RESERVES),

    # Treasury:
    'thor1qd4my7934h2sn5ag5eaqsde39va4ex2asz3yv5': ('Treasury Multisig', ThorRealms.TREASURY),
    'thor1505gp5h48zd24uexrfgka70fg8ccedafsnj0e3': ('Treasury 1', ThorRealms.TREASURY),
    'thor14n2q7tpemxcha8zc26j0g5pksx4x3a9xw9ryq9': ('Treasury 2', ThorRealms.TREASURY),
    'thor1egxvam70a86jafa8gcg3kqfmfax3s0m2g3m754': ('Treasury LP', ThorRealms.TREASURY),

    # CEX:
    "thor1t60f02r8jvzjrhtnjgfj4ne6rs5wjnejwmj7fh": ("Binance", ThorRealms.CEX),
    "thor1cqg8pyxnq03d88cl3xfn5wzjkguw5kh9enwte4": ("Binance", ThorRealms.CEX),
    "thor1uz4fpyd5f5d6p9pzk8lxyj4qxnwq6f9utg0e7k": ("Binance", ThorRealms.CEX),
    "thor1ty6h2ll07fqfzumphp6kq3hm4ps28xlm2l6kd6": ("crypto.com", ThorRealms.CEX),
    "thor1jw0nhlmj4lv83dwhfknqnw6tmlvgw4xyf6rgd7": ("KuCoin", ThorRealms.CEX),
    "thor1hy2ka6xmqjfcwagtplyttayug4eqpqhu0sdu6r": ("KuCoin", ThorRealms.CEX),
    "thor15h7uv2339vdzt2a6qsjf6uh5zc06sed7szvze5": ("Ascendex", ThorRealms.CEX),
    "thor1nm0rrq86ucezaf8uj35pq9fpwr5r82clphp95t": ("Kraken", ThorRealms.CEX),
}

MAYA_POOLS_URL = 'https://mayanode.mayachain.info/mayachain/pools'


class RuneHoldEntry(NamedTuple):
    address: str
    amount: int
    name: str
    realm: str

    def add_amount(self, amount):
        return self._replace(amount=self.amount + amount)


class RuneCirculatingSupply(NamedTuple):
    circulating: int
    total: int
    holders: Dict[str, RuneHoldEntry]

    @classmethod
    def zero(cls):
        return cls(0, 0, {})

    def set_holder(self, h: RuneHoldEntry):
        self.holders[h.address] = h

    @property
    def killed_switched(self):
        return RUNE_IDEAL_SUPPLY - RUNE_SUPPLY_AFTER_SWITCH

    @property
    def lending_burnt_rune(self):
        return RUNE_SUPPLY_AFTER_SWITCH - self.total - self.adr12_burnt_rune

    @property
    def adr12_burnt_rune(self):
        return RUBE_BURNT_ADR_12

    @property
    def total_burnt_rune(self):
        return RUNE_SUPPLY_AFTER_SWITCH - self.total

    def find_by_realm(self, realms, join_by_name=False):
        if isinstance(realms, str):
            realms = (realms,)
        items = [h for h in self.holders.values() if h.realm in realms]
        if join_by_name:
            name_dict = {}
            for item in items:
                if item.name in name_dict:
                    name_dict[item.name] = name_dict[item.name].add_amount(item.amount)
                else:
                    name_dict[item.name] = item
            return list(name_dict.values())
        return items

    def total_rune_in_realm(self, realms):
        return sum(h.amount for h in self.find_by_realm(realms))

    def __repr__(self) -> str:
        return f"RuneCirculatingSupply(circulating={self.circulating}, total={self.total}, holders={len(self.holders)})"

    @property
    def in_cex(self):
        return self.total_rune_in_realm(ThorRealms.CEX)

    @property
    def in_cex_percent(self):
        return self.in_cex / self.total * 100

    @property
    def treasury(self):
        return self.total_rune_in_realm(ThorRealms.TREASURY)

    @property
    def treasury_percent(self):
        return self.treasury / self.total * 100

    @property
    def in_reserves(self):
        return self.total_rune_in_realm((ThorRealms.RESERVES, ThorRealms.STANDBY_RESERVES))

    @property
    def bonded(self):
        return self.total_rune_in_realm(ThorRealms.BONDED)

    @property
    def bonded_percent(self):
        return self.bonded / self.total * 100

    @property
    def pooled(self):
        return self.total_rune_in_realm(ThorRealms.LIQ_POOL)

    @property
    def pooled_percent(self):
        return self.pooled / self.total * 100

    @property
    def pol(self):
        return self.total_rune_in_realm(ThorRealms.POL)

    @property
    def pol_percent(self):
        return self.pol / self.total * 100

    @property
    def runepool(self):
        return self.total_rune_in_realm(ThorRealms.RUNEPOOL)

    @property
    def runepool_percent(self):
        return self.runepool / self.total * 100

    @property
    def working(self):
        return self.bonded + self.pooled


class RuneCirculatingSupplyFetcher(WithLogger):
    def __init__(self, session, thor_node, step_sleep=0):
        super().__init__()
        self.session = session
        self.thor_node = thor_node
        self.step_sleep = step_sleep

    async def fetch(self) -> RuneCirculatingSupply:
        """
        @return: RuneCirculatingSupply
        """

        thor_rune_supply = await self.get_thor_rune_total_supply()
        result = RuneCirculatingSupply(thor_rune_supply, thor_rune_supply, {})

        for address, (wallet_name, realm) in THOR_ADDRESS_DICT.items():
            # No hurry, do it step by step
            await asyncio.sleep(self.step_sleep)

            balance = await self.get_thor_address_balance(address)
            result.set_holder(RuneHoldEntry(address, balance, wallet_name, realm))

        maya_pool_balance = await self.get_maya_pool_rune()
        result.set_holder(RuneHoldEntry('Maya pool', int(maya_pool_balance), 'Maya pool', ThorRealms.MAYA_POOL))

        locked_rune = sum(
            w.amount for w in result.holders.values()
            if w.realm in (ThorRealms.RESERVES, ThorRealms.STANDBY_RESERVES)
        )

        return RuneCirculatingSupply(
            thor_rune_supply - locked_rune, thor_rune_supply, result.holders
        )

    @staticmethod
    def get_pure_rune_from_thor_array(arr):
        if arr:
            thor_rune = next((item['amount'] for item in arr if item['denom'] == RUNE_DENOM), 0)
            # return int(int(thor_rune) / 10 ** RUNE_DECIMALS)
            return int(thor_to_float(thor_rune))
        else:
            return 0

    async def get_all_native_token_supplies(self):
        url_supply = f'{self.thor_node}/cosmos/bank/v1beta1/supply'
        self.logger.debug(f'Get: "{url_supply}"')
        async with self.session.get(url_supply) as resp:
            j = await resp.json()
            items = j['supply']
            return items

    async def get_thor_rune_total_supply(self):
        supplies = await self.get_all_native_token_supplies()
        return self.get_pure_rune_from_thor_array(supplies)

    async def get_thor_address_balance(self, address):
        url_balance = f'{self.thor_node}/cosmos/bank/v1beta1/balances/{address}'
        self.logger.debug(f'Get: "{url_balance}"')
        async with self.session.get(url_balance) as resp:
            j = await resp.json()
            return self.get_pure_rune_from_thor_array(j['balances'])

    async def get_maya_pool_rune(self):
        with suppress(Exception):
            async with self.session.get(MAYA_POOLS_URL) as resp:
                j = await resp.json()
                rune_pool = next(p for p in j if p['asset'] == 'THOR.RUNE')
                return thor_to_float(rune_pool['balance_asset'])
        return 0.0
