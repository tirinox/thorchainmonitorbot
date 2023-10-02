import asyncio
from typing import NamedTuple, Dict

from services.lib.constants import RUNE_IDEAL_SUPPLY, RUNE_SUPPLY_AFTER_SWITCH, RUNE_DECIMALS
from services.lib.utils import WithLogger


class ThorRealms:
    RESERVES = 'Reserves'
    UNDEPLOYED_RESERVES = 'Undeployed reserves'

    BONDED = 'Bonded'
    BONDED_NODE = 'Bonded (node)'
    POOLED = 'Pooled'
    CIRCULATING = 'Other circulating'

    CEX = 'CEX'
    BURNED = 'Burned'
    MINTED = 'Minted'
    TREASURY = 'Treasury'


THOR_ADDRESS_DICT = {
    # Reserves:
    'thor1dheycdevq39qlkxs2a6wuuzyn4aqxhve4qxtxt': (ThorRealms.RESERVES, ThorRealms.RESERVES),
    'thor1lj62pg6ryxv2htekqx04nv7wd3g98qf9gfvamy': (ThorRealms.UNDEPLOYED_RESERVES, ThorRealms.UNDEPLOYED_RESERVES),

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


class RuneHoldEntry(NamedTuple):
    address: str
    amount: int
    name: str
    realm: str


class RuneCirculatingSupply(NamedTuple):
    circulating: int
    total: int
    holders: Dict[str, RuneHoldEntry]

    @classmethod
    def zero(cls):
        return cls(0, 0, {})

    def set_holder(self, h: RuneHoldEntry):
        self.holders[h.address] = h

    @staticmethod
    def lost_forever():
        return RUNE_IDEAL_SUPPLY - RUNE_SUPPLY_AFTER_SWITCH

    @property
    def lending_burnt_rune(self):
        return RUNE_SUPPLY_AFTER_SWITCH - self.total

    def find_by_realm(self, realms):
        if isinstance(realms, str):
            realms = (realms,)
        return [h for h in self.holders.values() if h.realm in realms]

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
        return self.total_rune_in_realm((ThorRealms.RESERVES, ThorRealms.UNDEPLOYED_RESERVES))

    @property
    def bonded(self):
        return self.total_rune_in_realm(ThorRealms.BONDED)

    @property
    def bonded_percent(self):
        return self.bonded / self.total * 100

    @property
    def pooled(self):
        return self.total_rune_in_realm(ThorRealms.POOLED)

    @property
    def pooled_percent(self):
        return self.pooled / self.total * 100


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

        wallet_balances = {}
        for address, (wallet_name, realm) in THOR_ADDRESS_DICT.items():
            # No hurry, do it step by step
            await asyncio.sleep(self.step_sleep)

            balance = await self.get_thor_address_balance(address)

            wallet_balances[address] = RuneHoldEntry(
                address, balance, wallet_name, realm
            )

        locked_rune = sum(
            w.amount for w in wallet_balances.values()
            if w.realm in (ThorRealms.RESERVES, ThorRealms.UNDEPLOYED_RESERVES)
        )

        return RuneCirculatingSupply(
            thor_rune_supply - locked_rune, thor_rune_supply, wallet_balances
        )

    @staticmethod
    def get_pure_rune_from_thor_array(arr):
        if arr:
            thor_rune = next((item['amount'] for item in arr if item['denom'] == 'rune'), 0)
            return int(int(thor_rune) / 10 ** RUNE_DECIMALS)
        else:
            return 0

    async def get_thor_rune_total_supply(self):
        url_supply = f'{self.thor_node}/cosmos/bank/v1beta1/supply'
        self.logger.debug(f'Get: "{url_supply}"')
        async with self.session.get(url_supply) as resp:
            j = await resp.json()
            items = j['supply']
            return self.get_pure_rune_from_thor_array(items)

    async def get_thor_address_balance(self, address):
        url_balance = f'{self.thor_node}/cosmos/bank/v1beta1/balances/{address}'
        self.logger.debug(f'Get: "{url_balance}"')
        async with self.session.get(url_balance) as resp:
            j = await resp.json()
            return self.get_pure_rune_from_thor_array(j['balances'])
