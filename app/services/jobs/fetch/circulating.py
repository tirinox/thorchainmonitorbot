import asyncio
from dataclasses import dataclass
from typing import NamedTuple, Dict

from services.lib.constants import BNB_RUNE_SYMBOL_NO_CHAIN, RUNE_IDEAL_SUPPLY
from services.lib.utils import WithLogger

BEP2_RUNE_ASSET = BNB_RUNE_SYMBOL_NO_CHAIN
BEP2_RUNE_DECIMALS = 8
ERC20_RUNE_DECIMALS = 18

THOR_NODE_DEFAULT = 'https://thornode.ninerealms.com'

RUNE_ERC20_CONTRACT_ADDRESS = '0x3155BA85D5F96b2d030a4966AF206230e46849cb'
RUNE_ERC20_DEFAULT_SUPPLY = 9206991

THOR_ADDRESS_UNDEPLOYED_RESERVES = 'thor1lj62pg6ryxv2htekqx04nv7wd3g98qf9gfvamy'
THOR_ADDRESS_RESERVE_MODULE = 'thor1dheycdevq39qlkxs2a6wuuzyn4aqxhve4qxtxt'
THOR_ADDRESS_TEAM = 'thor1lrnrawjlfp6jyrzf39r740ymnuk9qgdgp29rqv'
THOR_ADDRESS_VESTED_9R = 'thor1y5lk3rzatghv9y4s4j90qt9ayq83e2dpf2hvzc'
THOR_ADDRESS_SEED = 'thor16qnm285eez48r4u9whedq4qunydu2ucmzchz7p'
THOR_ADDRESS_SEED_2 = 'thor16vwdn4h8p5c9cplp62hw7xg4r5rszh297h96h2'  # 5m from Seed went here, 1m to bonds


class ThorRealms:
    TEAM = 'Team'
    SEED = 'Seed'
    VESTING_9R = 'Vesting 9R'
    RESERVES = 'Reserves'
    UNDEPLOYED_RESERVES = 'Undeployed reserves'

    PREBURN = 'Preburn'
    ASGARD = 'Asgard'

    BONDED = 'Bonded'
    POOLED = 'Pooled'
    CIRCULATING = 'Circulating'


THOR_EXCLUDE_FROM_CIRCULATING_ADDRESSES = {
    ThorRealms.TEAM: THOR_ADDRESS_TEAM,
    ThorRealms.SEED: THOR_ADDRESS_SEED,
    ThorRealms.VESTING_9R: THOR_ADDRESS_VESTED_9R,
    ThorRealms.RESERVES: THOR_ADDRESS_RESERVE_MODULE,
    ThorRealms.UNDEPLOYED_RESERVES: THOR_ADDRESS_UNDEPLOYED_RESERVES
}


class SupplyEntry(NamedTuple):
    circulating: int
    total: int
    locked: Dict[str, int]

    @classmethod
    def zero(cls):
        return cls(0, 0, {})

    @property
    def locked_amount(self):
        return sum(self.locked.values())


@dataclass
class RuneCirculatingSupply:
    erc20_rune: SupplyEntry
    bep2_rune: SupplyEntry
    thor_rune: SupplyEntry
    overall: SupplyEntry

    @property
    def as_dict(self):
        return {
            'supply': {
                'ETH.RUNE': self.erc20_rune._asdict(),
                'BNB.RUNE': self.bep2_rune._asdict(),
                'THOR.RUNE': self.thor_rune._asdict(),
                'overall': self.overall._asdict()
            }
        }

    @classmethod
    def zero(cls):
        return cls(SupplyEntry.zero(), SupplyEntry.zero(), SupplyEntry.zero(), SupplyEntry.zero())

    @property
    def lost_forever(self):
        return RUNE_IDEAL_SUPPLY - self.thor_rune.total - self.bep2_rune.circulating - self.erc20_rune.circulating


class RuneCirculatingSupplyFetcher(WithLogger):
    def __init__(self, session, thor_exclude=None, thor_node=THOR_NODE_DEFAULT):
        super().__init__()
        self.session = session
        self.thor_exclude = thor_exclude or THOR_EXCLUDE_FROM_CIRCULATING_ADDRESSES
        self.thor_node = thor_node

    async def fetch(self, survive_progress=1.0) -> RuneCirculatingSupply:
        """
        @param survive_progress: float 0.0-1.0, 0.0 when the kill switch is finished,
        @return: RuneCirculatingSupply
        """

        thor_exclude_balance_group = asyncio.gather(
            *[self.get_thor_address_balance(address) for address in THOR_EXCLUDE_FROM_CIRCULATING_ADDRESSES.values()]
        )

        (
            thor_rune_supply,
            thor_exclude_balance_arr,
        ) = await asyncio.gather(
            self.get_thor_rune_total_supply(),
            thor_exclude_balance_group,
        )

        thor_locked_dict = dict((k, v) for k, v in
                                zip(THOR_EXCLUDE_FROM_CIRCULATING_ADDRESSES.keys(), thor_exclude_balance_arr))

        # noinspection PyTypeChecker
        thor_exclude_balance = sum(thor_exclude_balance_arr) if thor_exclude_balance_arr else 0
        thor_rune_circulating = thor_rune_supply - thor_exclude_balance
        thor_entry = SupplyEntry(thor_rune_circulating, thor_rune_supply, thor_locked_dict)
        return RuneCirculatingSupply(
            erc20_rune=SupplyEntry(0, 1, {}),
            bep2_rune=SupplyEntry(0, 1, {}),
            thor_rune=thor_entry,
            overall=thor_entry
        )

    @staticmethod
    def get_pure_rune_from_thor_array(arr):
        if arr:
            thor_rune = next(item['amount'] for item in arr if item['denom'] == 'rune')
            return int(int(thor_rune) / 10 ** BEP2_RUNE_DECIMALS)
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
