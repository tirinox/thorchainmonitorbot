from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.jobs.fetch.runeyield.base import AsgardConsumerConnectorBase
from services.jobs.fetch.runeyield.lp import AsgardConsumerConnectorV1
from services.jobs.fetch.runeyield.lp_v2 import AsgardConsumerConnectorV2
from services.lib.constants import NetworkIdents
from services.lib.depcont import DepContainer


def get_rune_yield_connector(deps: DepContainer, ppf: PoolPriceFetcher) -> AsgardConsumerConnectorBase:
    network_id = deps.cfg.network_id
    if network_id in (NetworkIdents.TESTNET_MULTICHAIN, NetworkIdents.CHAOSNET_MULTICHAIN):
        return AsgardConsumerConnectorV1(deps, ppf)
    elif network_id == NetworkIdents.CHAOSNET_BEP2CHAIN:
        return AsgardConsumerConnectorV2(deps, ppf)
    else:
        raise KeyError('unsupported network ID!')
