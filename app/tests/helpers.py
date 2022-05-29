import asyncio

import pytest

from services.lib.db import DB
from services.lib.depcont import DepContainer


@pytest.fixture(scope="function")
def fixture_deps():
    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.db = DB(d.loop)
    return d
