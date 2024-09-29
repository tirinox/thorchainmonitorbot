from jobs.runeyield.base import AsgardConsumerConnectorBase
from jobs.runeyield.lp_my import HomebrewLPConnector
from lib.depcont import DepContainer


def get_rune_yield_connector(deps: DepContainer) -> AsgardConsumerConnectorBase:
    return HomebrewLPConnector(deps)
