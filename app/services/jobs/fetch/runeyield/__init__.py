from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.jobs.fetch.runeyield.base import AsgardConsumerConnectorBase
from services.jobs.fetch.runeyield.lp import AsgardConsumerConnectorV1
from services.jobs.fetch.runeyield.lp_v2 import AsgardConsumerConnectorV2
from services.jobs.fetch.runeyield.lp_my import HomebrewLPConnector
from services.lib.midgard.urlgen import get_url_gen_by_network_id
from services.lib.constants import NetworkIdents
from services.lib.depcont import DepContainer


def get_rune_yield_connector(deps: DepContainer, ppf: PoolPriceFetcher) -> AsgardConsumerConnectorBase:
    network_id = deps.cfg.network_id
    url_gen = get_url_gen_by_network_id(network_id)
    if network_id in (NetworkIdents.TESTNET_MULTICHAIN, NetworkIdents.CHAOSNET_MULTICHAIN):
        # return AsgardConsumerConnectorV2(deps, ppf, url_gen)
        return HomebrewLPConnector(deps, ppf, url_gen)
    elif network_id == NetworkIdents.CHAOSNET_BEP2CHAIN:
        return AsgardConsumerConnectorV1(deps, ppf, url_gen)
    else:
        raise KeyError('unsupported network ID!')
