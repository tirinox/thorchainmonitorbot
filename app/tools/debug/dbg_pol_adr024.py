import asyncio
import json
import logging
from pathlib import Path

from jobs.fetch.pol_reserve import PolReserveFetcher
from comm.localization.languages import Language
from lib.texts import sep
from notify.pub_configure import PublicAlertJobExecutor
from tools.lib.lp_common import LpAppFramework

DEMO_DIR = Path(__file__).resolve().parents[2] / 'renderer' / 'demo'


async def dbg_fetch(app: LpAppFramework, days=PolReserveFetcher.MAX_DAYS):
    fetcher = PolReserveFetcher(app.deps, days=days)
    data = await fetcher.fetch()

    sep('Current')
    cur = data.current
    print(f'Height {cur.height}, {cur.usd_per_rune = :.4f}, undeployed {cur.undeployed_rune}')
    print(f'Deposited {cur.rune_deposited:,.0f} R, value {cur.value_rune:,.0f} R = ${cur.value_usd:,.0f}, '
          f'PnL {cur.pnl_percent:+.2f}%')
    for p in cur.pools:
        print(f'  {p.asset[:24]:24} dep {p.rune_deposited_float:>12,.0f} R | value {p.value_rune:>12,.0f} R | '
              f'share {p.share_percent:5.1f}% | deeper {p.deeper_percent:5.1f}% | '
              f'{p.rune_held:,.0f} R + {p.asset_held:,.2f} asset')

    sep('Days')
    for d in data.days:
        print(f'{d.date}{"*" if d.partial else " "} dep {d.deposited_rune:>10,.0f} R | cum {d.cumulative_deposited_rune:>10,.0f} | '
              f'value {d.value_rune:>10,.0f} R | ${d.usd_per_rune:.4f} | income {d.system_income_rune:>10,.0f} | '
              f'fees {d.fees_rune:>9,.1f} | net {d.earnings_rune:>8,.1f}')

    sep('Summary')
    print(f'System income share: {data.system_income_percent}%, max deployment {data.max_deployment_rune} R/block')
    print(f'Avg daily deposit: {data.avg_daily_deposit_rune:,.0f} R; deposited at cost ${data.deposited_usd_at_cost:,.0f}')
    print(f'Fees total: {data.fees_rune():,.0f} R gross / {data.fees_rune(net=True):,.0f} R net')
    for n in (1, 7, 30):
        print(f'APR {n}d: gross {data.apr_percent(n)}, net {data.apr_percent(n, net=True)}')
    return data


async def dbg_save_demo(app: LpAppFramework):
    """Makes the demo parameters of the infographic out of the live data"""
    fetcher = PolReserveFetcher(app.deps)
    data = await fetcher.fetch()

    # pretend the previous alert was posted at the end of the day before yesterday
    day = data.complete_days[-2]
    data.previous = await fetcher._load_cached_day_end(day.date)
    data.previous.usd_per_rune = day.usd_per_rune

    path = DEMO_DIR / 'pol_summary_adr024.json'
    with open(path, 'w') as f:
        json.dump({'template_name': 'pol_summary_adr024.jinja2', 'parameters': data.to_dict()}, f, indent=2)
    print(f'Saved to {path}')


async def dbg_texts(app: LpAppFramework, data=None):
    data = data or await PolReserveFetcher(app.deps).fetch()
    data.previous = await PolReserveFetcher(app.deps)._load_cached_day_end(data.complete_days[-2].date)
    data.previous.usd_per_rune = data.complete_days[-2].usd_per_rune
    for lang in (Language.ENGLISH, Language.RUSSIAN, Language.ENGLISH_TWITTER):
        sep(lang)
        loc = app.deps.loc_man[lang]
        text = loc.notification_text_pol_reserve_stats(data)
        print(text)
        print(f'({len(text)} symbols)')


async def dbg_render(app: LpAppFramework, data, local_renderer=True):
    """Renders the infographic the same way the alert does, but saves it to a file instead of sending"""
    loc = app.deps.loc_man[Language.ENGLISH]
    presenter = app.deps.alert_presenter
    if local_renderer:
        # outside of Docker the "renderer" host of the config is not resolvable
        presenter.renderer.url = 'http://127.0.0.1:8404/render'
    photo, photo_name = await presenter.render_pol_reserve_stats(loc, data)
    path = Path(__file__).resolve().parents[3] / 'temp' / photo_name
    with open(path, 'wb') as f:
        f.write(photo.getvalue() if hasattr(photo, 'getvalue') else photo)
    print(f'Saved to {path}')


async def dbg_send_alert(app: LpAppFramework):
    """Runs the whole job: the alert goes to the channels of the config!"""
    executor = PublicAlertJobExecutor(app.deps)
    await executor.job_pol_summary_adr024()
    await asyncio.sleep(5)


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        data = await dbg_fetch(app)
        await dbg_texts(app, data)
        await dbg_render(app, data)
        # await dbg_save_demo(app)
        # await dbg_send_alert(app)


if __name__ == '__main__':
    asyncio.run(main())
