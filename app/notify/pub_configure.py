from typing import Optional

from jobs.fetch.pol import RunePoolFetcher
from jobs.fetch.secured_asset import SecuredAssetAssetFetcher
from jobs.fetch.tcy import TCYInfoFetcher
from lib.depcont import DepContainer
from lib.logs import WithLogger
from lib.prev_state import PrevStateDB
from models.runepool import AlertRunepoolStats, POLState, AlertPOLState, RunepoolState
from notify.pub_scheduler import PublicScheduler


class PubAlertJobNames:
    SECURED_ASSET_SUMMARY = "secured_asset_summary"
    TCY_SUMMARY = "tcy_summary"
    POL_SUMMARY = "pol_summary"
    RUNE_POOL_SUMMARY = "runepool_summary"


class PublicAlertJobExecutor(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.tcy_info_fetcher = TCYInfoFetcher(deps)
        self.secured_asset_fetcher = SecuredAssetAssetFetcher(deps)
        self.runepool_fetcher = RunePoolFetcher(deps)

    async def _send_alert(self, data, alert_type: str):
        if not data:
            raise Exception(f"No data for {alert_type}")
        await self.deps.alert_presenter.handle_data(data)

    async def job_tcy_summary(self):
        data = await self.tcy_info_fetcher.fetch()
        await self._send_alert(data, "tcy summary alert")

    async def job_secured(self):
        data = await self.secured_asset_fetcher.fetch()
        await self._send_alert(data, "secured asset summary alert")

    async def job_pol_summary(self):
        pvdb = PrevStateDB(self.deps.db, POLState)
        previous: Optional[POLState] = await pvdb.get()

        data: AlertPOLState = await self.runepool_fetcher.fetch()

        data = data._replace(previous=previous if previous else None)

        await self._send_alert(data, "POL summary alert")

        await pvdb.set(data.current)

    async def job_runepool_summary(self):
        data = await self.runepool_fetcher.fetch()
        usd_per_rune = await self.deps.pool_cache.get_usd_per_rune()

        pvdb = PrevStateDB(self.deps.db, RunepoolState)
        previous: Optional[RunepoolState] = await pvdb.get()

        runepool_event = AlertRunepoolStats(
            data.runepool,
            previous,
            usd_per_rune=usd_per_rune,
        )

        # AlertRunepoolStats
        await self._send_alert(runepool_event, "runepool summary alert")

        await pvdb.set(data.runepool)

    # maps job names to methods of this class
    AVAILABLE_TYPES = {
        PubAlertJobNames.TCY_SUMMARY: job_tcy_summary,
        PubAlertJobNames.SECURED_ASSET_SUMMARY: job_secured,
        PubAlertJobNames.POL_SUMMARY: job_pol_summary,
        PubAlertJobNames.RUNE_POOL_SUMMARY: job_runepool_summary,
    }

    async def configure_jobs(self):
        d = self.deps
        scheduler = d.public_scheduler = PublicScheduler(d.cfg, d.db, d.loop)
        for job_name, job_func in self.AVAILABLE_TYPES.items():
            await scheduler.register_job_type(job_name, job_func.__get__(self))
        return scheduler
