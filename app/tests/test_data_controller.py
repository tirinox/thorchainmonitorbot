from types import SimpleNamespace

from jobs.fetch.base import BaseFetcher, DataController
from jobs.fetch.net_stats import NetworkStatisticsFetcher


class _Fetcher(BaseFetcher):
    async def fetch(self):
        return None


def _deps():
    cfg = SimpleNamespace(net_summary=SimpleNamespace(fetch_period='125s'), sleep_step=0.1)
    return SimpleNamespace(data_controller=DataController(), cfg=cfg)


def test_a_later_instance_does_not_replace_the_registered_one():
    deps = _deps()
    running = _Fetcher(deps, 60)
    helper = _Fetcher(deps, 60)

    assert deps.data_controller.summary == {'_Fetcher': running}

    # unregistering the helper must not drop the running fetcher either
    deps.data_controller.unregister(helper)
    assert deps.data_controller.summary == {'_Fetcher': running}

    deps.data_controller.unregister(running)
    assert deps.data_controller.summary == {}


def test_net_stats_fetcher_zero_period_is_one_off():
    deps = _deps()
    running = NetworkStatisticsFetcher(deps)
    assert running.sleep_period == 125

    one_off = NetworkStatisticsFetcher(deps, 0)
    assert one_off.sleep_period == 0
    assert deps.data_controller.summary == {'NetworkStatisticsFetcher': running}
