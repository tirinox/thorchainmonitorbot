from typing import List

from api.aionode.types import ThorRunePool
from api.midgard.parser import get_parser_by_network_id
from api.midgard.urlgen import free_url_gen
from jobs.fetch.base import BaseFetcher
from lib.constants import bp_to_percent, thor_to_float
from lib.date_utils import parse_timespan_to_seconds
from lib.depcont import DepContainer
from models.mimir_naming import MIMIR_KEY_POL_TARGET_SYNTH_PER_POOL_DEPTH, MIMIR_KEY_POL_MAX_NETWORK_DEPOSIT
from models.pool_member import PoolMemberDetails
from models.runepool import AlertPOLState, POLState, RunepoolState


class RunePoolFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer, reserve_address=None):
        period = parse_timespan_to_seconds(deps.cfg.runepool.fetch_period)
        super().__init__(deps, period)
        self.reserve_address = reserve_address or deps.cfg.native_scanner.reserve_address
        self.midgard_parser = get_parser_by_network_id(deps.cfg.network_id)

    async def get_reserve_membership(self, reserve=None) -> List[PoolMemberDetails]:
        reserve = reserve or self.reserve_address
        member_details = await self.deps.midgard_connector.request(
            free_url_gen.url_for_address_pool_membership(reserve))

        if not member_details:
            self.logger.warning(f'Reserve address is not member of pools')
            return []

        details = self.midgard_parser.parse_pool_member_details(member_details, reserve)
        details.sort(key=lambda d: d.pool)
        return details

    async def load_runepool(self, ago_sec=0) -> ThorRunePool:
        height = 0
        if ago_sec:
            height = await self.deps.last_block_cache.get_thor_block_time_ago(ago_sec)
        runepool = await self.deps.thor_connector.query_runepool(height)
        return runepool

    async def fetch(self) -> AlertPOLState:
        mimir = self.deps.mimir_const_holder

        synth_target = mimir.get_constant(MIMIR_KEY_POL_TARGET_SYNTH_PER_POOL_DEPTH, 4500)
        synth_target = bp_to_percent(synth_target)
        max_deposit = thor_to_float(mimir.get_constant(MIMIR_KEY_POL_MAX_NETWORK_DEPOSIT, 10e3, float))

        rune_providers = await self.deps.thor_connector.query_runepool_providers()
        avg_deposit = sum(p.rune_value for p in rune_providers) / len(
            rune_providers) if rune_providers else 0.0

        runepool = await self.load_runepool()
        if runepool.pol.value > 0:
            membership = await self.get_reserve_membership(self.reserve_address)
        else:
            membership = []

        self.logger.info(f"Got RunePOOL: {runepool}, providers: {len(rune_providers)}.")

        return AlertPOLState(
            POLState(self.deps.price_holder.usd_per_rune, runepool.pol),
            membership,
            prices=self.deps.price_holder,
            mimir_max_deposit=max_deposit,
            mimir_synth_target_ptc=synth_target,
            runepool=RunepoolState(
                runepool,
                n_providers=len(rune_providers),
                avg_deposit=avg_deposit,
                usd_per_rune=self.deps.price_holder.usd_per_rune,
            ),
        )
