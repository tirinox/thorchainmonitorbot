import os

import redis


def get_redis(prefix):
    host = os.getenv(f'{prefix}_REDIS_HOST')
    port = int(os.getenv(f'{prefix}_REDIS_PORT'))
    db = int(os.getenv(f'{prefix}_REDIS_DB'))
    password = os.getenv(f'{prefix}_REDIS_PASSWORD')
    r = redis.StrictRedis(
        host=host,
        port=port,
        db=db,
        password=password,
        decode_responses=True
    )
    try:
        r.ping()
        print(f'Connected to {prefix} Redis ({host}:{port}/{db})')
        return r
    except Exception as e:
        print(f'Error connecting to {prefix} Redis:', e)
        return None
