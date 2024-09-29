import asyncio

import pytest

from lib.db import DB
from lib.depcont import DepContainer


@pytest.fixture(scope="function")
def fixture_deps():
    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.db = DB(d.loop)
    return d
