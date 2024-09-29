from jobs.fetch.runeyield.base import AsgardConsumerConnectorBase
from jobs.fetch.runeyield.lp_my import HomebrewLPConnector
from lib.depcont import DepContainer


def get_rune_yield_connector(deps: DepContainer) -> AsgardConsumerConnectorBase:
    return HomebrewLPConnector(deps)
