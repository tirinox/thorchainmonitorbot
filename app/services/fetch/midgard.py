from services.lib.config import Config

MIDGARD_V1 = 'v1'
MIDGARD_V2 = 'v2'
MIDGARD_DEFAULT_VERSION = MIDGARD_V2

DEFAULT_MIDGARD_URL = 'https://chaosnet-midgard.bepswap.com'
DEFAULT_MIDGARD_TEST_URL = 'https://testnet.midgard.thorchain.info'


def get_midgard_url(cfg: Config, path: str, version=MIDGARD_DEFAULT_VERSION):
    try:
        base_url = cfg.midgard.api_url
    except KeyError:
        base_url = DEFAULT_MIDGARD_URL
    base_url = base_url.rstrip('/')
    path = path.lstrip('/')
    full_path = f"{base_url}/{version}/{path}"
    return full_path
