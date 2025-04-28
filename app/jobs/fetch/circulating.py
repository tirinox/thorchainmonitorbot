import asyncio

from aiohttp import ClientSession

from api.aionode.connector import ThorConnector
from api.maya import MayaConnector
from api.midgard.connector import MidgardConnector
from lib.constants import thor_to_float, RUNE_DENOM, \
    THOR_ADDRESS_DICT, ThorRealms, TREASURY_LP_ADDRESS
from lib.logs import WithLogger
from models.circ_supply import RuneCirculatingSupply, RuneHoldEntry
from models.mimir_naming import MIMIR_KEY_MAX_RUNE_SUPPLY


class RuneCirculatingSupplyFetcher(WithLogger):
    def __init__(self, session: ClientSession, thor: ThorConnector, midgard: MidgardConnector, step_sleep=0):
        super().__init__()
        self.session = session
        self.thor = thor
        self.step_sleep = step_sleep
        self.midgard = midgard
        self.maya = MayaConnector(session)

    async def fetch(self) -> RuneCirculatingSupply:
        """
        @return: RuneCirculatingSupply
        """

        thor_rune_supply = await self.get_thor_rune_total_supply()  # Actual current Rune supply
        thor_rune_max_supply = await self.get_max_supply_from_mimir()  # 500M - burned income part = mimir MaxRuneSupply

        result = RuneCirculatingSupply(
            thor_rune_supply,
            thor_rune_max_supply, {}
        )

        for address, (wallet_name, realm) in THOR_ADDRESS_DICT.items():
            # No hurry, do it step by step
            await asyncio.sleep(self.step_sleep)

            balance = await self.get_thor_address_balance(address)

            # fixme: other treasury addresses also hold some LP!
            # if address == TREASURY_LP_ADDRESS:
            #     lp_balance = await self.get_treasury_lp_value()
            #     self.logger.info(f'Treasury LP balance ({address}): {lp_balance} Rune')
            #     balance += lp_balance

            result.set_holder(RuneHoldEntry(address, balance, wallet_name, realm))

        maya_pool_balance = await self.maya.get_maya_pool_rune()
        result.set_holder(RuneHoldEntry('Maya pool', int(maya_pool_balance), 'Maya pool', ThorRealms.MAYA_POOL))

        return result

        # locked_rune = sum(
        #     w.amount for w in result.holders.values()
        #     if w.realm in (ThorRealms.RESERVES, ThorRealms.STANDBY_RESERVES)
        # )
        # circulating_rune = thor_rune_supply - locked_rune
        #
        # return result._replace(circulating=circulating_rune)

    @staticmethod
    def get_pure_rune_from_thor_array(arr):
        if arr:
            thor_rune = next((item['amount'] for item in arr if item['denom'] == RUNE_DENOM), 0)
            return int(thor_to_float(thor_rune))
        else:
            return 0

    @property
    def thor_node_base_url(self):
        return self.thor.env.thornode_url

    async def get_all_native_token_supplies(self):
        url_supply = f'{self.thor_node_base_url}/cosmos/bank/v1beta1/supply'
        self.logger.debug(f'Get: "{url_supply}"')
        supply = await self.thor.query_raw('/cosmos/bank/v1beta1/supply')
        return supply['supply']

    async def get_thor_rune_total_supply(self):
        supplies = await self.get_all_native_token_supplies()
        return self.get_pure_rune_from_thor_array(supplies)

    async def get_thor_address_balance(self, address):
        url_balance = f'/cosmos/bank/v1beta1/balances/{address}'
        self.logger.debug(f'Get: "{url_balance}"')
        j = await self.thor.query_raw(url_balance)
        return self.get_pure_rune_from_thor_array(j['balances'])

    async def get_treasury_lp_value(self, address=TREASURY_LP_ADDRESS):
        tr_lp = await self.midgard.query_pool_membership(address, show_savers=True)
        pools = await self.midgard.query_pools()
        rune_accum = 0.0
        for member in tr_lp:
            if member.pool in pools:
                rune_accum += pools[member.pool].total_my_capital_of_pool_in_rune(member.liquidity_units)
        return rune_accum

    async def get_max_supply_from_mimir(self):
        mimir = await self.thor.query_mimir()
        if mimir:
            return int(thor_to_float(mimir[MIMIR_KEY_MAX_RUNE_SUPPLY]))
