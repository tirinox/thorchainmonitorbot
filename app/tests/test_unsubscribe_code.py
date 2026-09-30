from types import SimpleNamespace

import pytest

from notify.personal.scheduled import PersonalIdTriplet, PersonalPeriodicNotificationService
from tests.fakes import FakeDB

OWNER = '42'
GROUP = '-1001234567890'  # Telegram group ids are negative
POOL = 'ETH.USDT-0XDAC17F958D2EE523A2206206994597C13D831EC7'  # pool names may contain '-'


class FakeScheduler:
    def __init__(self):
        self.active = set()

    async def schedule(self, ident, period=None):
        self.active.add(ident)

    async def cancel(self, ident):
        self.active.discard(ident)


def _service():
    return PersonalPeriodicNotificationService(SimpleNamespace(db=FakeDB(), scheduler=FakeScheduler()))


async def _subscribe(service, user_id):
    tr = PersonalIdTriplet(user_id, 'thor1address', POOL)
    await service.subscribe(tr, period=3600)
    return tr, await service._retrieve_unsub_id(tr)


@pytest.mark.parametrize('key, expected', [
    (f'{OWNER}-thor1address-{POOL}', (OWNER, 'thor1address', POOL)),
    (f'{GROUP}-thor1address-{POOL}', (GROUP, 'thor1address', POOL)),
    ('C0123SLACK-thor1address-BTC.BTC', ('C0123SLACK', 'thor1address', 'BTC.BTC')),
])
def test_key_round_trip(key, expected):
    tr = PersonalIdTriplet.from_key(key)
    assert tuple(tr) == expected
    assert tr.as_key == key


def test_not_a_key():
    with pytest.raises(ValueError):
        PersonalIdTriplet.from_key('Ab3dE')


@pytest.mark.asyncio
async def test_owner_can_unsubscribe():
    service = _service()
    tr, code = await _subscribe(service, OWNER)

    assert await service.unsubscribe_by_id(code, int(OWNER)) is True
    assert tr.as_key not in service.deps.scheduler.active


@pytest.mark.asyncio
async def test_another_chat_cannot_unsubscribe():
    service = _service()
    tr, code = await _subscribe(service, OWNER)

    assert await service.unsubscribe_by_id(code, 43) is False
    assert tr.as_key in service.deps.scheduler.active
    # and the code still works for the owner
    assert await service.unsubscribe_by_id(code, OWNER) is True


@pytest.mark.asyncio
async def test_subscription_key_is_not_a_code():
    # the code map works both ways, so a key typed in as a code finds the code; it must not break anything
    service = _service()
    tr, code = await _subscribe(service, OWNER)

    assert await service.unsubscribe_by_id(tr.as_key, OWNER) is False
    assert tr.as_key in service.deps.scheduler.active
    assert await service._retrieve_unsub_id(tr) == code


@pytest.mark.asyncio
async def test_group_chat_can_unsubscribe():
    service = _service()
    tr, code = await _subscribe(service, GROUP)

    assert await service.unsubscribe_by_id(code, OWNER) is False
    assert await service.unsubscribe_by_id(code, int(GROUP)) is True
    assert tr.as_key not in service.deps.scheduler.active


@pytest.mark.asyncio
async def test_unknown_code():
    assert await _service().unsubscribe_by_id('zzzzz', OWNER) is False


@pytest.mark.asyncio
async def test_temporary_failures_do_not_unsubscribe():
    service = _service()
    tr, _ = await _subscribe(service, OWNER)
    errors = []

    async def failing_report(_tr):
        raise ConnectionError('Midgard is down')

    async def record_error(details, _tr, unsubscribed=True):
        errors.append(unsubscribed)

    service._deliver_report = failing_report
    service._deliver_error_message = record_error

    for _ in range(service.max_report_fails - 1):
        await service._deliver_report_safe(tr)
        assert tr.as_key in service.deps.scheduler.active
    assert errors == [False] * (service.max_report_fails - 1)

    # a success in between resets the counter
    async def good_report(_tr):
        pass

    service._deliver_report = good_report
    await service._deliver_report_safe(tr)

    service._deliver_report = failing_report
    for _ in range(service.max_report_fails - 1):
        await service._deliver_report_safe(tr)
    assert tr.as_key in service.deps.scheduler.active

    await service._deliver_report_safe(tr)  # the last straw
    assert tr.as_key not in service.deps.scheduler.active
    assert errors[-1] is True
    assert await service.deps.db.redis.hget(service.DB_KEY_FAILS, tr.as_key) is None
