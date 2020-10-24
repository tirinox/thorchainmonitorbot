import pytest

from services.config import Config
from services.notify.types.queue_notify import QueueNotifier

class FakeConfig(Config):
    def __init__(self):
        ...


def setup():
    print("basic setup into module")


@pytest.fixture
def cfg():
    return FakeConfig()


def teardown():
    print("basic teardown into module")


async def test1(mocker, cfg):

    f = QueueNotifier(cfg, None)
    await f.fetch()