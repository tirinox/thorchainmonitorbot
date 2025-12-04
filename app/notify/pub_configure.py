from typing import Optional

from jobs.fetch.key_stats import KeyStatsFetcher
from jobs.fetch.pol import RunePoolFetcher
from jobs.fetch.pool_price import PoolInfoFetcherMidgard
from jobs.fetch.secured_asset import SecuredAssetAssetFetcher
from jobs.fetch.tcy import TCYInfoFetcher
from jobs.fetch.trade_accounts import TradeAccountFetcher
from jobs.rune_burn_recorder import RuneBurnRecorder
from lib.date_utils import DAY
from lib.depcont import DepContainer
from lib.logs import WithLogger
from lib.prev_state import PrevStateDB
from models.circ_supply import RuneCirculatingSupply
from models.key_stats_model import AlertKeyStats
from models.pool_info import EventPools, PoolMapStruct
from models.price import PriceHolder, RuneMarketInfo
from models.runepool import AlertRunepoolStats, POLState, AlertPOLState, RunepoolState
from models.trade_acc import AlertTradeAccountStats
from notify.pub_scheduler import PublicScheduler
from notify.public.cex_flow import CEXFlowRecorder
from notify.public.price_notify import PriceChangeNotifier


class PubAlertJobNames:
    SECURED_ASSET_SUMMARY = "secured_asset_summary"
    TCY_SUMMARY = "tcy_summary"
    POL_SUMMARY = "pol_summary"
    RUNE_POOL_SUMMARY = "runepool_summary"
    KEY_METRICS = "key_metrics"
    TOP_POOLS = "top_pools"
    SUPPLY_CHART = "supply_chart"
    RUNE_BURN_CHART = "rune_burn_chart"
    TRADE_ASSET_SUMMARY = "trade_account_summary"

    PRICE_ALERT = "price_alert"
    RUNE_CEX_FLOW = "rune_cex_flow"


class PublicAlertJobExecutor(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.tcy_info_fetcher = TCYInfoFetcher(deps)
        self.secured_asset_fetcher = SecuredAssetAssetFetcher(deps)
        self.runepool_fetcher = RunePoolFetcher(deps)
        self.key_stats_fetcher = KeyStatsFetcher(deps)
        self.trade_acc_fetcher = TradeAccountFetcher(deps)
        self.cex_flow_recorder = CEXFlowRecorder(deps)

    async def _send_alert(self, data, alert_type: str):
        if not data:
            raise Exception(f"No data for {alert_type}")
        await self.deps.alert_presenter.handle_data(data)

    async def job_tcy_summary(self):
        data = await self.tcy_info_fetcher.fetch()
        await self._send_alert(data, "tcy summary alert")

    async def job_secured_asset_summary(self):
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

        await self._send_alert(runepool_event, "runepool summary alert")

        await pvdb.set(data.runepool)

    async def job_key_metrics(self):
        data: AlertKeyStats = await self.key_stats_fetcher.fetch()
        if not data.current.btc_total_usd:
            raise ValueError(f'No pool data! Aborting.')

        if not data or not data.previous.btc_total_usd:
            self.logger.warning(f'No previous pool data! Go on')

        await self._send_alert(data, "key metrics infographic")

    async def job_top_pools(self):
        income_intervals = 7
        income_period = 'day'

        earnings = await self.deps.midgard_connector.query_earnings(count=income_intervals * 2 + 1,
                                                                    interval=income_period)

        mdg_pool_fetcher = PoolInfoFetcherMidgard(self.deps, 1.0)
        pool_map_struct = await mdg_pool_fetcher.fetch_as_pool_map_struct()
        if not pool_map_struct or not pool_map_struct.pool_map:
            raise ValueError("No pools loaded!")

        pvdb = PrevStateDB(self.deps.db, PoolMapStruct)
        prev_pool_map = await pvdb.get()

        usd_per_rune = PriceHolder(self.deps.cfg.stable_coins).calculate_rune_price_here(pool_map_struct.pool_map)
        if not usd_per_rune:
            raise ValueError("Rune price is not available!")

        event_pools = EventPools(
            pool_map_struct.pool_map, prev_pool_map.pool_map,
            earnings,
            usd_per_rune=usd_per_rune
        )

        await self._send_alert(event_pools, "top pools alert")
        await pvdb.set(pool_map_struct)

    async def job_supply_chart(self):
        market_info: RuneMarketInfo = await self.deps.market_info_cache.get()

        if not market_info or not (supply := market_info.supply_info):
            raise ValueError(f'Market Info is incomplete: {market_info = }. Ignoring!')

        if not supply.bonded or not supply.pooled:
            raise ValueError(f'Supply Info is incomplete: {supply.pooled = }, {supply.bonded = }. Ignoring!')

        pvdb = PrevStateDB(self.deps.db, RuneCirculatingSupply)
        market_info.prev_supply_info = await pvdb.get()

        await self._send_alert(market_info, "circulating supply alert")
        await pvdb.set(market_info.supply_info)

    async def job_rune_burn_chart(self):
        recorder = RuneBurnRecorder(self.deps)
        if not (event := await recorder.get_event()):
            raise ValueError("No rune burn event data available!")
        await self._send_alert(event, "rune burn chart alert")

    async def job_trade_account_summary(self):
        data: AlertTradeAccountStats = await self.trade_acc_fetcher.fetch()
        await self._send_alert(data, "trade account stats")

    async def job_price_alert(self):
        pn = PriceChangeNotifier(self.deps)
        pn.price_graph_period = 7 * DAY
        market_info: RuneMarketInfo = await self.deps.market_info_cache.get()
        alert = await pn.make_event(
            market_info,
            ath=False, last_ath=None
        )
        await self._send_alert(alert, "price alert")

    async def job_rune_cex_flow(self):
        flow = await self.cex_flow_recorder.get_event(period=DAY)
        if not flow:
            self.deps.emergency.report('CEXFlow', 'No CEX flow')
            raise Exception("No CEX flow data available.")

        if flow.total_rune < self.cex_flow_recorder.min_rune_in_summary:
            self.deps.emergency.report(
                'CEXFlow', 'CEX flow is lower than the minimum rune in summary.',
                flow=flow,
                min_rune=self.cex_flow_recorder.min_rune_in_summary,
            )
            raise Exception("CEX flow is lower than the minimum rune in summary.")

        await self._send_alert(flow, "rune cex flow alert")

    # maps job names to methods of this class
    AVAILABLE_TYPES = {
        PubAlertJobNames.TCY_SUMMARY: job_tcy_summary,
        PubAlertJobNames.SECURED_ASSET_SUMMARY: job_secured_asset_summary,
        PubAlertJobNames.POL_SUMMARY: job_pol_summary,
        PubAlertJobNames.RUNE_POOL_SUMMARY: job_runepool_summary,
        PubAlertJobNames.KEY_METRICS: job_key_metrics,
        PubAlertJobNames.TOP_POOLS: job_top_pools,
        PubAlertJobNames.SUPPLY_CHART: job_supply_chart,
        PubAlertJobNames.RUNE_BURN_CHART: job_rune_burn_chart,
        PubAlertJobNames.TRADE_ASSET_SUMMARY: job_trade_account_summary,
        PubAlertJobNames.PRICE_ALERT: job_price_alert,
        PubAlertJobNames.RUNE_CEX_FLOW: job_rune_cex_flow,
    }

    async def configure_jobs(self):
        d = self.deps
        scheduler = d.public_scheduler = PublicScheduler(d.cfg, d.db, d.loop)
        for job_name, job_func in self.AVAILABLE_TYPES.items():
            await scheduler.register_job_type(job_name, job_func.__get__(self))
        return scheduler
