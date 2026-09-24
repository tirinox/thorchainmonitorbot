import asyncio
import logging

from lib.depcont import DepContainer
from lib.money import DepthCurve
from notify.dup_stop import TxDeduplicator
from notify.pub_scheduler import PublicScheduler
from notify.public.tx_notify import SwapTxNotifier, LiquidityTxNotifier
from tools.lib.lp_common import LpAppFramework

DEDUPLICATOR_NAMES = [
    'scanner:last_seen', 'route:seen_tx', 'TxCount', 'VolumeRecorder',
    'RunePool:announced-hashes', 'ss-started:announced-hashes', 'TradeAcc:announced-hashes',
    'large-tx:announced-hashes',
]


class DashboardContext:
    """
    Long-lived state of the dashboard process: the app framework (deps) and helper objects
    that are expensive or pointless to recreate on every request.
    """

    def __init__(self, app: LpAppFramework):
        self.app = app
        d = self.deps

        self.deduplicators = {name: TxDeduplicator(d.db, name) for name in DEDUPLICATOR_NAMES}

        curve_pts = d.cfg.get_pure('tx.curve', default=DepthCurve.DEFAULT_TX_VS_DEPTH_CURVE)
        curve = DepthCurve(curve_pts)
        self.swap_notifier = SwapTxNotifier(d, d.cfg.tx.swap, curve=curve)
        self.liquidity_notifier = LiquidityTxNotifier(d, d.cfg.tx.liquidity, curve=curve)

        # serializes read-modify-write operations on the scheduler config
        self.sched_lock = asyncio.Lock()

    @property
    def deps(self) -> DepContainer:
        return self.app.deps

    @property
    def scheduler(self) -> PublicScheduler:
        return self.deps.pub_scheduler

    @classmethod
    async def create(cls) -> 'DashboardContext':
        loop = asyncio.get_running_loop()

        app = LpAppFramework(log_level=logging.INFO)
        # App.__init__ installs a fresh event loop; we must keep using uvicorn's running loop
        asyncio.set_event_loop(loop)
        d = app.deps
        d.loop = loop
        if d.data_controller:
            # never overwrite fetcher stats that the bot process writes
            d.data_controller.enabled = False

        await app.prepare()
        await d.pub_scheduler.start_rpc_client()
        logging.info('Dashboard context initialized')
        return cls(app)

    async def close(self):
        await self.app.close()
