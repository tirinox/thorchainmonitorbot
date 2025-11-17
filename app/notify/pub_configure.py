from jobs.fetch.secured_asset import SecuredAssetAssetFetcher
from lib.depcont import DepContainer
from models.types import PubAlertJobNames
from notify.pub_scheduler import PublicScheduler


async def configure_scheduled_public_notifications(d: DepContainer) -> PublicScheduler:
    d.public_scheduler = p = PublicScheduler(d.cfg, d.db)

    secured_asset_fetcher = SecuredAssetAssetFetcher(d)

    async def job_secured():
        data = await secured_asset_fetcher.fetch()
        if not data:
            raise Exception("No data fetched for secured asset summary alert")
        await d.alert_presenter.handle_data(data)

    await p.register_job_type(PubAlertJobNames.SECURED_ASSET_SUMMARY, job_secured)

    return p
