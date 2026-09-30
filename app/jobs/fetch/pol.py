from api.aionode.types import ThorRunePool
from jobs.fetch.base import BaseFetcher
from lib.date_utils import parse_timespan_to_seconds, now_ts
from lib.depcont import DepContainer
from models.runepool import AlertPOLState, POLState, RunepoolState


class POLAndRunePoolFetcher(BaseFetcher):
    """
    RUNEPool and the legacy POL of the Reserve behind it.
    The system income funded POL (ADR-024) is another thing: see PolReserveFetcher.
    """

    def __init__(self, deps: DepContainer):
        period = parse_timespan_to_seconds(deps.cfg.runepool.fetch_period)
        super().__init__(deps, period)

    async def load_runepool(self, ago_sec=0) -> ThorRunePool:
        height = 0
        if ago_sec:
            height = await self.deps.last_block_cache.get_thor_block_time_ago(ago_sec)
        runepool = await self.deps.thor_connector.query_runepool(height)
        return runepool

    async def fetch(self) -> AlertPOLState:
        rune_providers = await self.deps.thor_connector.query_runepool_providers()
        avg_deposit = sum(p.rune_value for p in rune_providers) / len(
            rune_providers) if rune_providers else 0.0

        runepool = await self.load_runepool()

        self.logger.info(f"Got RunePOOL: {runepool}, providers: {len(rune_providers)}.")

        ph = await self.deps.pool_cache.get()

        now = int(now_ts())
        return AlertPOLState(
            POLState(ph.usd_per_rune, runepool.pol, now),
            prices=ph,
            runepool=RunepoolState(
                runepool,
                n_providers=len(rune_providers),
                avg_deposit=avg_deposit,
                usd_per_rune=ph.usd_per_rune,
                timestamp=now,
            ),
        )
