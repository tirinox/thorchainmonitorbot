import asyncio
from dataclasses import dataclass
from typing import NamedTuple

BEP2_RUNE_ASSET = 'RUNE-B1A'

BEP2_BURN_ADDRESS = 'bnb1e4q8whcufp6d72w8nwmpuhxd96r4n0fstegyuy'
BEP2_OPS_ADDRESS = 'bnb13a7gyv5zl57c0rzeu0henx6d0tzspvrrakxxtv'  # about 1.2m rune

BEP2_EXCLUDE_FROM_CIRCULATING_ADDRESSES = [
    BEP2_BURN_ADDRESS,
]

RUNE_ERC20_CONTRACT_ADDRESS = '0x3155BA85D5F96b2d030a4966AF206230e46849cb'
RUNE_ERC20_DEFAULT_SUPPLY = 9206991

THOR_ADDRESS_UNDEPLOYED_RESERVES = 'thor1lj62pg6ryxv2htekqx04nv7wd3g98qf9gfvamy'
THOR_ADDRESS_RESERVE_MODULE = 'thor1dheycdevq39qlkxs2a6wuuzyn4aqxhve4qxtxt'
THOR_ADDRESS_TEAM = 'thor1lrnrawjlfp6jyrzf39r740ymnuk9qgdgp29rqv'
THOR_ADDRESS_SEED = 'thor16qnm285eez48r4u9whedq4qunydu2ucmzchz7p'

THOR_EXCLUDE_FROM_CIRCULATING_ADDRESSES = [
    THOR_ADDRESS_TEAM,
    THOR_ADDRESS_SEED,
    THOR_ADDRESS_RESERVE_MODULE,
    THOR_ADDRESS_UNDEPLOYED_RESERVES
]


def url_bep2_token_info(start=0, limit=1000):
    return f'https://dex.binance.org/api/v1/tokens?limit={limit}&offset={start}'


def url_bep2_get_balance(address):
    return f'https://dex.binance.org/api/v1/account/{address}'


URL_THOR_SUPPLY = 'https://thornode.ninerealms.com/cosmos/bank/v1beta1/supply'


def url_thor_get_balance(address):
    return f'https://thornode.ninerealms.com/cosmos/bank/v1beta1/balances/{address}'


def url_etherscan_supply_erc20(contract, api_key):
    return f'https://api.etherscan.io/api?module=stats&action=tokensupply&contractaddress={contract}&apikey={api_key}'


def get_pure_rune_from_thor_array(arr):
    thor_rune = next(item['amount'] for item in arr if item['denom'] == 'rune')
    return int(int(thor_rune) / 10 ** 8)


async def get_thor_rune_total_supply(session):
    async with session.get(URL_THOR_SUPPLY) as resp:
        j = await resp.json()
        items = j['supply']
        return get_pure_rune_from_thor_array(items)


async def get_bnb_rune_total_supply(session):
    async with session.get(url_bep2_token_info()) as resp:
        j = await resp.json()
        rune_entry = next(item for item in j if item['symbol'] == BEP2_RUNE_ASSET)
        return int(float(rune_entry['total_supply']))


async def get_erc20_rune_total_supply(session, ether_scan_api_key):
    if ether_scan_api_key:
        async with session.get(url_etherscan_supply_erc20(RUNE_ERC20_CONTRACT_ADDRESS, ether_scan_api_key)) as resp:
            j = await resp.json()
            return int(int(j['result']) / 10 ** 18)
    else:
        return RUNE_ERC20_DEFAULT_SUPPLY  # if no key use last known value


async def get_bep2_address_balance(session, address):
    async with session.get(url_bep2_get_balance(address)) as resp:
        j = await resp.json()
        for balance in j['balances']:
            if balance['symbol'] == BEP2_RUNE_ASSET:
                free = float(balance['free'])
                frozen = float(balance['frozen'])
                locked = float(balance['locked'])
                return int(frozen + free + locked)
        return 0


async def get_thor_address_balance(session, address):
    async with session.get(url_thor_get_balance(address)) as resp:
        j = await resp.json()
        return get_pure_rune_from_thor_array(j['balances'])


class SupplyEntry(NamedTuple):
    circulating: int
    total: int


@dataclass
class RuneCirculatingSupply:
    erc20_rune: SupplyEntry
    bep2_rune: SupplyEntry
    thor_rune: SupplyEntry
    overall: SupplyEntry


class RuneCirculatingSupplyFetcher:
    def __init__(self,
                 session,
                 ether_scan_key=None,
                 bep2_exclude=None, thor_exclude=None,
                 rune_contract=RUNE_ERC20_CONTRACT_ADDRESS):
        self.session = session
        self.bep2_exclude = bep2_exclude or BEP2_EXCLUDE_FROM_CIRCULATING_ADDRESSES
        self.thor_exclude = thor_exclude or THOR_EXCLUDE_FROM_CIRCULATING_ADDRESSES
        self.rune_contract = rune_contract
        self._ether_scan_key = ether_scan_key

    async def fetch(self):
        session = self.session
        bep2_exclude_balance_arr = await asyncio.gather(
            *[get_bep2_address_balance(session, address) for address in BEP2_EXCLUDE_FROM_CIRCULATING_ADDRESSES],
        )
        bep2_exclude_balance = sum(bep2_exclude_balance_arr) if bep2_exclude_balance_arr else 0

        thor_exclude_balance_arr = await asyncio.gather(
            *[get_thor_address_balance(session, address) for address in THOR_EXCLUDE_FROM_CIRCULATING_ADDRESSES]
        )
        thor_exclude_balance = sum(thor_exclude_balance_arr) if thor_exclude_balance_arr else 0

        data = await asyncio.gather(
            get_thor_rune_total_supply(session),
            get_erc20_rune_total_supply(session, self._ether_scan_key),
            get_bnb_rune_total_supply(session),
        )
        thor_rune_supply, erc20_rune_supply, bep2_rune_supply = data

        erc20_rune_circulating = erc20_rune_supply
        bep2_rune_circulating = bep2_rune_supply - bep2_exclude_balance
        thor_rune_circulating = thor_rune_supply - thor_exclude_balance

        total_supply = erc20_rune_supply + bep2_rune_supply + thor_rune_supply
        total_circulating = erc20_rune_supply + thor_rune_circulating + bep2_rune_supply

        return RuneCirculatingSupply(
            erc20_rune=SupplyEntry(erc20_rune_circulating, erc20_rune_supply),
            bep2_rune=SupplyEntry(bep2_rune_circulating, bep2_rune_supply),
            thor_rune=SupplyEntry(thor_rune_circulating, thor_rune_supply),
            overall=SupplyEntry(total_circulating, total_supply)
        )
