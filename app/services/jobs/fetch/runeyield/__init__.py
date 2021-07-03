from services.jobs.fetch.runeyield.base import AsgardConsumerConnectorBase
from services.jobs.fetch.runeyield.lp_my import HomebrewLPConnector
from services.lib.depcont import DepContainer
from services.lib.midgard.urlgen import get_url_gen_by_network_id


def get_rune_yield_connector(deps: DepContainer) -> AsgardConsumerConnectorBase:
    network_id = deps.cfg.network_id
    url_gen = get_url_gen_by_network_id(network_id)
    return HomebrewLPConnector(deps, url_gen)
