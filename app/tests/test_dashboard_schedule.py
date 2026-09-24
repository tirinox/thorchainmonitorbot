from datetime import datetime, timezone, date

import pytest

from dashboard.services.schedule import (
    describe_cron, describe_interval, convert_times, preview_schedule, get_scheduler_timezone, job_schedule_info,
)
from models.sched import SchedJobCfg
from notify.pub_scheduler import PublicScheduler
from tests.fakes import FakeDB, FakePubSubRedis

# Wednesday
NOW = datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize('cron, text', [
    ({'minute': '*/10'}, 'Every 10 minutes'),
    ({'minute': '*/1'}, 'Every minute'),
    ({'hour': '9'}, 'At 09:00 every day'),  # APScheduler: omitted minute/second become 0
    ({'hour': '9,18', 'day_of_week': 'mon-fri'}, 'At 09:00 and 18:00, on weekdays'),
    ({'minute': '30'}, 'Every hour at :30'),
    ({'minute': '0'}, 'Every hour'),
    ({'minute': '0,30'}, 'Every hour at :00 and :30'),
    ({'minute': '0', 'hour': '*/4'}, 'Every 4 hours at :00'),
    ({'day': '1', 'hour': '0'}, 'At 00:00, on the 1st of the month'),
    ({'day': 'last', 'hour': '23', 'minute': '55'}, 'At 23:55, on the last day of the month'),
    ({'minute': '*/15', 'hour': '9-17', 'day_of_week': 'mon-fri'},
     'Every 15 minutes between 09:00 and 17:59, on weekdays'),
    ({'hour': '8-20', 'minute': '0'}, 'Every hour at :00 from 08:00 to 20:00'),
    ({'day_of_week': 'sat,sun', 'hour': '12'}, 'At 12:00, on weekends'),
    ({'day_of_week': 'wed', 'hour': '14', 'minute': '5'}, 'At 14:05, on Wednesdays'),
    ({'day_of_week': 'mon,wed,fri', 'hour': '10'}, 'At 10:00, on Mon, Wed and Fri'),
    ({'month': '1,7', 'day': '1', 'hour': '0'}, 'At 00:00, on the 1st of the month, in January and July'),
    ({'day': '2,3,22'}, 'At 00:00, on the 2nd, 3rd and 22nd of the month'),
    ({'second': '*/30'}, 'Every 30 seconds'),
    ({'hour': '9', 'minute': '0', 'second': '15'}, 'At 09:00:15 every day'),
    # second is the least significant field set, so minute stays "*": every minute of hour 9
    ({'hour': '9', 'second': '15'}, 'Every minute at second 15 between 09:00 and 09:59'),
    ({'minute': '*/5', 'hour': '9,18'}, 'Every 5 minutes during hours 9 and 18'),
])
def test_describe_cron(cron, text):
    assert describe_cron(cron)[0] == text


def test_describe_cron_returns_fixed_times_only_for_daily_times():
    assert describe_cron({'hour': '9,18'})[1] == ['09:00', '18:00']
    assert describe_cron({'minute': '*/10'})[1] is None


def test_tz_relevance():
    from dashboard.services.schedule import describe_schedule
    assert not describe_schedule('cron', None, {'minute': '*/10'}, None, 'UTC')['tz_relevant']
    assert describe_schedule('cron', None, {'hour': '9'}, None, 'UTC')['tz_relevant']
    assert not describe_schedule('interval', {'hours': 1}, None, None, 'UTC')['tz_relevant']


def test_describe_interval():
    assert describe_interval({'hours': 1}) == 'Every hour'
    assert describe_interval({'minutes': 6}) == 'Every 6 minutes'
    assert describe_interval({'hours': 1, 'minutes': 30}) == 'Every 1 hour 30 minutes'
    assert describe_interval({'weeks': 2, 'days': 0}) == 'Every 2 weeks'


def test_convert_times_to_viewer_timezone():
    on = date(2026, 9, 23)
    assert convert_times(['09:00', '23:30'], 'UTC', 'Europe/Istanbul', on) == [
        {'time': '12:00', 'day_shift': 0}, {'time': '02:30', 'day_shift': 1},
    ]
    assert convert_times(['01:00'], 'UTC', 'America/New_York', on) == [{'time': '21:00', 'day_shift': -1}]
    assert convert_times(['09:00'], 'UTC', 'Etc/UTC', on) is None  # same offset: nothing to add
    assert convert_times(['09:00'], 'UTC', 'Not/AZone', on) is None


def test_preview_cron_next_runs_follow_apscheduler():
    p = preview_schedule('cron', None, {'hour': '9,18', 'day_of_week': 'mon-fri'}, None, 'UTC', now=NOW)
    assert p['ok'] and p['warning'] is None
    runs = [datetime.fromtimestamp(t, timezone.utc).strftime('%a %H:%M') for t in p['next_runs']]
    assert runs == ['Wed 18:00', 'Thu 09:00', 'Thu 18:00', 'Fri 09:00', 'Fri 18:00']


def test_preview_uses_the_scheduler_timezone():
    p = preview_schedule('cron', None, {'hour': '9'}, None, 'Europe/Istanbul', now=NOW)
    first = datetime.fromtimestamp(p['next_runs'][0], timezone.utc)
    assert first.hour == 6  # 09:00 in Istanbul (UTC+3)


def test_preview_errors_and_warnings():
    bad = preview_schedule('cron', None, {'minute': '*/70'}, None, 'UTC', now=NOW)
    assert not bad['ok'] and 'step value (70)' in bad['error']
    assert not preview_schedule('cron', None, {'minute': 'abc'}, None, 'UTC', now=NOW)['ok']
    assert not preview_schedule('interval', {'hours': 0}, None, None, 'UTC', now=NOW)['ok']

    past = preview_schedule('date', None, None, {'run_date': '2020-01-01T00:00:00Z'}, 'UTC', now=NOW)
    assert past['ok'] and 'past' in past['warning']

    interval = preview_schedule('interval', {'minutes': 30}, None, None, 'UTC', now=NOW)
    assert interval['schedule']['text'] == 'Every 30 minutes' and 'applied' in interval['warning']
    assert len(interval['next_runs']) == 5


def test_job_schedule_info_marks_invalid_jobs():
    job = SchedJobCfg(id='j', func='f', variant='cron', cron={'minute': '*/70'})
    info = job_schedule_info(job, 'UTC')
    assert info['invalid'] and info['text'].startswith('Invalid schedule')


@pytest.mark.asyncio
async def test_scheduler_timezone_comes_from_the_bot():
    redis = FakePubSubRedis()
    db = FakeDB(redis)
    assert await get_scheduler_timezone(db)  # falls back to this machine's zone

    await redis.set(PublicScheduler.DB_KEY_TIMEZONE, 'Etc/UTC')
    assert await get_scheduler_timezone(db) == 'UTC'
    await redis.set(PublicScheduler.DB_KEY_TIMEZONE, 'Europe/Istanbul')
    assert await get_scheduler_timezone(db) == 'Europe/Istanbul'
