import asyncio
import os
from io import BytesIO
from time import time

import matplotlib.pyplot as plt
import seaborn as sns

from services.fetch.queue import QueueFetcher
from services.lib.config import Config
from services.lib.datetime import DAY, HOUR
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.lib.utils import series_to_pandas
from services.models.time_series import TimeSeries
import pandas as pd


def save_pic(file_path='~/sns_test.png'):
    img = BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)

    with open(os.path.expanduser(file_path), 'wb') as f:
        f.write(img.getvalue())


async def points(d: DepContainer):
    ts = TimeSeries(QueueFetcher.QUEUE_TIME_SERIES, d.db)
    points = await ts.select(*ts.range_from_ago_to_now(DAY, tolerance_sec=10))
    df = series_to_pandas(points, shift_time=False)
    df["t"] = pd.to_datetime(df["t"], unit='s')

    f, ax = plt.subplots(1, 1)

    ax.plot_date(df["t"], df["outbound_queue"], color="blue", label="outbound_queue", linestyle="-")
    ax.plot_date(df["t"], df["swap_queue"], color="green", label="swap_queue", linestyle="-")

    x_dates = df['t'].dt.strftime('%H:%M').sort_values().unique()
    ax.set_xticklabels(labels=x_dates, rotation=45, ha='right')

    ax.legend()

    plt.show()


async def test_plots(d):
    await points(d)


if __name__ == '__main__':
    sns.set_theme(style="darkgrid")

    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.cfg = Config(Config.DEFAULT_LVL_UP)
    d.db = DB(d.loop)

    d.loop.run_until_complete(test_plots(d))
