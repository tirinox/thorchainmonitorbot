from datetime import datetime, timedelta, date

import pandas as pd

MINUTE = 60
HOUR = 60 * 60
DAY = 24 * 60 * 60
MONTH = 30 * 24 * 60 * 60


def now_ts() -> float:
    return datetime.now().timestamp()  # don't use utcnow() since timestamp() does this conversion


def seconds_diff(t1: datetime, t2: datetime) -> float:
    return (t1 - t2).total_seconds()


def seconds_human(seconds, translate=None) -> str:
    seconds = int(seconds)

    def tr(key):
        return translate.get(key, key) if translate else key

    def append_if_not_zero(acc, val, time_type):
        return acc if val == 0 else "{} {} {}".format(acc, val, time_type)

    if seconds == 0:
        return tr('just now')
    else:
        minutes = seconds // 60
        hours = minutes // 60
        days = hours // 24

        s = ''
        s = append_if_not_zero(s, days, tr('day') if days == 1 else tr('days'))
        if days <= 31:
            s = append_if_not_zero(s, hours % 24, tr('hour') if hours == 1 else tr('hours'))
        if not days:
            s = append_if_not_zero(s, minutes % 60, tr('min'))
        if not hours:
            s = append_if_not_zero(s, seconds % 60, tr('sec'))
        return s.strip()


LONG_AGO = datetime(1980, 1, 1)


def parse_timespan_to_seconds(span: str):
    try:
        return int(span)
    except ValueError:
        result = 0
        str_for_number = ''
        for symbol in span:
            symbol = symbol.lower()
            if symbol in ['d', 'h', 'm', 's']:
                if str_for_number:
                    try:
                        number = int(str_for_number)
                    except ValueError:
                        return 'Error! Invalid number: {}'.format(str_for_number)
                    else:
                        multipliers = {
                            's': 1,
                            'm': 60,
                            'h': 3600,
                            'd': 3600 * 24
                        }
                        result += multipliers[symbol] * number
                    finally:
                        str_for_number = ''
                else:
                    return 'Error! Must be some digits before!'
            elif symbol in [chr(i + ord('0')) for i in range(10)]:
                str_for_number += symbol
            elif symbol in [' ', ',', ';', ':', '\t', '/', '.']:
                pass
            else:
                return 'Error! Unexpected symbol: {}'.format(symbol)

        if str_for_number:
            return 'Error! Unfinished component in the end: {}'.format(str_for_number)

        return result


def format_time_ago(d, max_time=30*DAY, translate=None):
    def tr(key):
        return translate.get(key, key) if translate else key

    if d is None or d == 0:
        return tr('never')
    elif abs(d) < 5:
        return tr('just now')
    elif abs(d) > max_time:
        return tr('long-long ago')
    else:
        return f'{seconds_human(d, translate=translate)} {tr("ago")}'


def format_time_ago_short(d, now=None):
    now = now or now_ts()
    seconds = int(d - now)
    if seconds < 0:
        return "-" + format_time_ago_short(now, d)

    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24
    days = f'{days}d ' if days else ''
    minutes = minutes % 60
    hours = hours % 24
    return f'{days}{hours:02}:{minutes:02}'


def ts_event_points_to_pandas(ts_result, shift_time=True):
    normal_data = []
    zero_t = None
    for key, value_d in ts_result:
        key = key.split('-')
        event_id = int(key[1])
        if event_id > 99:
            continue

        # ms -> sec; + up to 100 events 0.01 sec each
        time_point = float(key[0]) / 1000.0 + 0.01 * event_id
        if zero_t is None:
            zero_t = time_point

        values = {
            k: float(v) for k, v in value_d.items()
        }

        normal_data.append({
            "t": (time_point - zero_t) if shift_time else time_point,
            **values
        })
    return pd.DataFrame(normal_data)


def ts_simple_points_to_pandas(points):
    timestamps, values = list(zip(*points))
    index = pd.to_datetime(timestamps, unit='s')
    return pd.DataFrame(values, index=index)


def today_str():
    now = datetime.now()
    return now.strftime("%d-%m-%Y--%H-%M-%S")


def days_ago_noon(days_ago, now=None, hour=12) -> datetime:
    now = now or datetime.now()
    day_back = now - timedelta(days=days_ago)
    day_back_noon = day_back.replace(hour=hour, minute=0, second=0, microsecond=0)
    return day_back_noon


def day_to_key(day: date, prefix=''):
    if day is None:
        day = datetime.now().date()
    return f'{prefix}:{day.year}.{day.month}.{day.day}'


def date_parse_rfc_z_no_ms(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ")


def date_parse_rfc(s: str):
    s = s.rstrip('Z')
    s = s[:-3]
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f")
