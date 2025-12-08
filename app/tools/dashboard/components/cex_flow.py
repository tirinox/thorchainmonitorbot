from lib.date_utils import DAY
from notify.public.cex_flow import CEXFlowRecorder


async def cex_flow_dashboard_info(d):
    cex_flow_notifier = CEXFlowRecorder(d)
    flow = await cex_flow_notifier.read_within_period(period=DAY)
    return flow
