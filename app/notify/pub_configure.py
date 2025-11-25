from jobs.fetch.secured_asset import SecuredAssetAssetFetcher
from jobs.fetch.tcy import TCYInfoFetcher
from lib.depcont import DepContainer
from lib.logs import WithLogger
from notify.pub_scheduler import PublicScheduler


class PubAlertJobNames:
    SECURED_ASSET_SUMMARY = "secured_asset_summary"
    TCY_SUMMARY = "tcy_summary"


AVAILABLE_SCHEDULER_JOBS = [
    PubAlertJobNames.SECURED_ASSET_SUMMARY,
    PubAlertJobNames.TCY_SUMMARY,
]


class PublicAlertJobExecutor(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.tcy_info_fetcher = TCYInfoFetcher(deps)
        self.secured_asset_fetcher = SecuredAssetAssetFetcher(deps)

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

    async def configure_jobs(self):
        d = self.deps
        scheduler = d.public_scheduler = PublicScheduler(d.cfg, d.db, d.loop)

        await scheduler.register_job_type(PubAlertJobNames.TCY_SUMMARY, self.job_tcy_summary)
        await scheduler.register_job_type(PubAlertJobNames.SECURED_ASSET_SUMMARY, self.job_secured)

        return scheduler
