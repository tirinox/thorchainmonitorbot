import asyncio
from dataclasses import dataclass
from typing import NamedTuple, Dict

from services.lib.constants import BNB_RUNE_SYMBOL_NO_CHAIN, RUNE_IDEAL_SUPPLY
from services.lib.utils import WithLogger

BEP2_RUNE_ASSET = BNB_RUNE_SYMBOL_NO_CHAIN
BEP2_RUNE_DECIMALS = 8
ERC20_RUNE_DECIMALS = 18

THOR_NODE_DEFAULT = 'https://thornode.ninerealms.com'

BEP2_BURN_ADDRESS = 'bnb1e4q8whcufp6d72w8nwmpuhxd96r4n0fstegyuy'
BEP2_OPS_ADDRESS = 'bnb13a7gyv5zl57c0rzeu0henx6d0tzspvrrakxxtv'  # about 1.2m rune

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
    ERC20 = 'ERC20'
    BEP2 = 'BEP2'
    KILLED = 'Killed'


THOR_EXCLUDE_FROM_CIRCULATING_ADDRESSES = {
    ThorRealms.TEAM: THOR_ADDRESS_TEAM,
    ThorRealms.SEED: THOR_ADDRESS_SEED,
    ThorRealms.VESTING_9R: THOR_ADDRESS_VESTED_9R,
    ThorRealms.RESERVES: THOR_ADDRESS_RESERVE_MODULE,
    ThorRealms.UNDEPLOYED_RESERVES: THOR_ADDRESS_UNDEPLOYED_RESERVES
}

BEP2_EXCLUDE_FROM_CIRCULATING_ADDRESSES = {
    ThorRealms.PREBURN: BEP2_BURN_ADDRESS,
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
    def __init__(self, session, ether_scan_key=None, bep2_exclude=None, thor_exclude=None,
                 rune_contract=RUNE_ERC20_CONTRACT_ADDRESS, thor_node=THOR_NODE_DEFAULT):
        super().__init__()
        self.session = session
        self.bep2_exclude = bep2_exclude or BEP2_EXCLUDE_FROM_CIRCULATING_ADDRESSES
        self.thor_exclude = thor_exclude or THOR_EXCLUDE_FROM_CIRCULATING_ADDRESSES
        self.rune_contract = rune_contract
        self.thor_node = thor_node
        self._ether_scan_key = ether_scan_key

    async def fetch(self, survive_progress=1.0) -> RuneCirculatingSupply:
        """
        @param survive_progress: float 0.0-1.0, 0.0 when the kill switch is finished,
        @return: RuneCirculatingSupply
        """
        bep2_exclude_balance_group = asyncio.gather(
            *[self.get_bep2_address_balance(address)
              for address in BEP2_EXCLUDE_FROM_CIRCULATING_ADDRESSES.values()],
        )

        thor_exclude_balance_group = asyncio.gather(
            *[self.get_thor_address_balance(address)
              for address in THOR_EXCLUDE_FROM_CIRCULATING_ADDRESSES.values()]
        )

        (
            thor_rune_supply,
            erc20_rune_supply,
            bep2_rune_supply,
            bep2_exclude_balance_arr,
            thor_exclude_balance_arr,
            (erc20_to_burn_asgard, bep2_to_burn_asgard),
        ) = await asyncio.gather(
            self.get_thor_rune_total_supply(),
            self.get_erc20_rune_total_supply(self._ether_scan_key),
            self.get_bnb_rune_total_supply(),
            bep2_exclude_balance_group,
            thor_exclude_balance_group,
            self.get_asgard_rune_to_burn(),
        )

        bep2_locked_dict = dict((k, v) for k, v in
                                zip(BEP2_EXCLUDE_FROM_CIRCULATING_ADDRESSES.keys(), bep2_exclude_balance_arr))
        bep2_locked_dict[ThorRealms.ASGARD] = bep2_to_burn_asgard

        thor_locked_dict = dict((k, v) for k, v in
                                zip(THOR_EXCLUDE_FROM_CIRCULATING_ADDRESSES.keys(), thor_exclude_balance_arr))

        erc20_locked_dict = {
            ThorRealms.ASGARD: erc20_to_burn_asgard
        }
        overall_locked_dict = {
            **bep2_locked_dict,
            **erc20_locked_dict,
            **thor_locked_dict,
            ThorRealms.ASGARD: erc20_to_burn_asgard + bep2_to_burn_asgard
        }

        # noinspection PyTypeChecker
        bep2_exclude_balance = sum(bep2_exclude_balance_arr) if bep2_exclude_balance_arr else 0
        bep2_exclude_balance += bep2_to_burn_asgard
        # noinspection PyTypeChecker
        thor_exclude_balance = sum(thor_exclude_balance_arr) if thor_exclude_balance_arr else 0
        erc20_exclude_balance = erc20_to_burn_asgard

        erc20_rune_circulating = erc20_rune_supply - erc20_exclude_balance
        bep2_rune_circulating = bep2_rune_supply - bep2_exclude_balance
        thor_rune_circulating = thor_rune_supply - thor_exclude_balance

        # total_supply = erc20_rune_supply + bep2_rune_supply + thor_rune_supply

        # < 500m Rune
        total_supply = (erc20_rune_circulating + bep2_rune_circulating) * survive_progress + thor_rune_supply
        total_circulating = (erc20_rune_supply + bep2_rune_supply) * survive_progress + thor_rune_circulating

        return RuneCirculatingSupply(
            erc20_rune=SupplyEntry(erc20_rune_circulating, erc20_rune_supply, erc20_locked_dict),
            bep2_rune=SupplyEntry(bep2_rune_circulating, bep2_rune_supply, bep2_locked_dict),
            thor_rune=SupplyEntry(thor_rune_circulating, thor_rune_supply, thor_locked_dict),
            overall=SupplyEntry(total_circulating, total_supply, overall_locked_dict)
        )

    @staticmethod
    def url_bep2_token_info(start=0, limit=1000):
        return f'https://dex.binance.org/api/v1/tokens?limit={limit}&offset={start}'

    @staticmethod
    def url_bep2_get_balance(address):
        return f'https://dex.binance.org/api/v1/account/{address}'

    @staticmethod
    def url_etherscan_supply_erc20(contract, api_key):
        return f'https://api.etherscan.io/api?module=stats&action=tokensupply&contractaddress={contract}&apikey={api_key}'

    async def get_bnb_rune_total_supply(self):
        url = self.url_bep2_token_info()
        self.logger.debug(f'Get: "{url}"')
        async with self.session.get(url) as resp:
            j = await resp.json()
            rune_entry = next(item for item in j if item['symbol'] == BEP2_RUNE_ASSET)
            return int(float(rune_entry['total_supply']))

    async def get_erc20_rune_total_supply(self, ether_scan_api_key):
        if ether_scan_api_key:
            url = self.url_etherscan_supply_erc20(RUNE_ERC20_CONTRACT_ADDRESS, ether_scan_api_key)
            async with self.session.get(url) as resp:
                j = await resp.json()
                return int(int(j['result']) / 10 ** ERC20_RUNE_DECIMALS)
        else:
            return 9206991  # if no key use last known value

    async def get_bep2_address_balance(self, address):
        url = self.url_bep2_get_balance(address)
        self.logger.debug(f'Get: "{url}"')
        async with self.session.get(url) as resp:
            j = await resp.json()
            for balance in j['balances']:
                if balance['symbol'] == BEP2_RUNE_ASSET:
                    free = float(balance['free'])
                    frozen = float(balance['frozen'])
                    locked = float(balance['locked'])
                    return int(frozen + free + locked)
            return 0

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

    async def get_asgard_coins(self):
        url_asgard = f'{self.thor_node}/thorchain/vaults/asgard'
        self.logger.debug(f'Get: "{url_asgard}"')
        async with self.session.get(url_asgard) as resp:
            j = await resp.json()
            compiled = {}
            for asgard in j:
                for coin in asgard['coins']:
                    asset = coin['asset']
                    amount = int(coin['amount'])
                    decimals = int(coin.get('decimals', 8))
                    if asset not in compiled:
                        compiled[asset] = {
                            'asset': asset,
                            'decimals': decimals,
                            'amount': 0
                        }
                    compiled[asset]['amount'] += amount

            return compiled

    async def get_asgard_rune_to_burn(self):
        data = await self.get_asgard_coins()

        erc20_asset = data.get(f'ETH.RUNE-{self.rune_contract.upper()}', {})
        bep2_asset = data.get(f'BNB.{BEP2_RUNE_ASSET}', {})

        erc20_to_burn = int(erc20_asset.get('amount', 0) / (10 ** erc20_asset.get('decimals', 8)))
        bep2_to_burn = int(bep2_asset.get('amount', 0) / (10 ** bep2_asset.get('decimals', 8)))
        return erc20_to_burn, bep2_to_burn
