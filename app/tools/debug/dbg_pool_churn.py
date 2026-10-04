import asyncio
import json
import logging

from comm.localization.eng_base import EnglishLocalization
from comm.localization.rus import RussianLocalization
from comm.picture.pool_card import build_pool_activated_card, POOL_ACTIVATED_TEMPLATE
from lib.config import Config
from lib.constants import DOGE_SYMBOL, BTC_SYMBOL, ETH_SYMBOL
from lib.depcont import DepContainer
from models.pool_info import PoolInfo
from notify.broadcast import Broadcaster
from notify.public.pool_churn_notify import PoolChurnNotifier
from tools.lib.lp_common import LpAppFramework

SAVE_GALLERY_DEMOS = False  # writes renderer/demo/pool_activated.json and pool_activated_ru.json, no network needed


async def dbg_simulate_pool_churn(d: DepContainer):
    """
    Two pools get activated (two cards, one after another) and one is suspended (a text).
    The cards need infographic_renderer.use_html_renderer and a running renderer.
    """
    d.broadcaster = Broadcaster(d)

    notifier_pool_churn = PoolChurnNotifier(d)
    notifier_pool_churn.add_subscriber(d.alert_presenter)

    ph = await d.pool_cache.get()

    before = ph.clone()
    before.pool_info_map[DOGE_SYMBOL].status = PoolInfo.STAGED
    before.pool_info_map[BTC_SYMBOL].status = PoolInfo.STAGED
    await notifier_pool_churn.on_data(None, before)  # the first look only remembers the pools

    after = ph.clone()
    after.pool_info_map[ETH_SYMBOL].status = PoolInfo.SUSPENDED

    await notifier_pool_churn.spam_cd.clear()
    await notifier_pool_churn.on_data(None, after)
    await asyncio.sleep(5)


def save_gallery_demos(usd_per_rune=2.5):
    """The parameters of the demos come from synthetic pools; the gallery is at http://127.0.0.1:8404/render/demo"""
    def pool_map(pool, rune, asset):
        pools = {pool: PoolInfo(pool, int(1e8 * asset), int(1e8 * rune), 1, PoolInfo.AVAILABLE)}
        pools.update({f'AVAX.TOKEN{i}': PoolInfo(f'AVAX.TOKEN{i}', 1, 1, 1, PoolInfo.AVAILABLE) for i in range(28)})
        return pools

    cfg = Config()
    demos = (
        ('pool_activated', EnglishLocalization(cfg), 'BSC.USDC-0X8AC76A51CC950D9822D68B83FE1AD97B32CD580D', 'BSC.BNB',
         1_050_000, 2_600_000, False,
         {'title': 'Pool activated: a token', 'subtitle': 'BSC.USDC, with the chain badge and the contract, trading is on',
          'lang': 'en', 'order': 0}),
        ('pool_activated_ru', RussianLocalization(cfg), 'BTC.BTC', '', 9_000_000, 1500, True,
         {'title': 'Pool activated: a gas asset', 'subtitle': 'BTC.BTC in Russian, no chain badge, trading is paused',
          'lang': 'ru', 'order': 1}),
    )
    for name, loc, pool, chain_logo, rune, asset, trading_paused, meta in demos:
        parameters = build_pool_activated_card(pool, pool_map(pool, rune, asset), usd_per_rune, loc, chain_logo,
                                               trading_paused=trading_paused)
        demo = {'template_name': POOL_ACTIVATED_TEMPLATE, 'meta': meta, 'parameters': parameters}
        with open(f'renderer/demo/{name}.json', 'w', encoding='utf-8') as f:
            json.dump(demo, f, indent=1, ensure_ascii=False)


async def main():
    if SAVE_GALLERY_DEMOS:
        save_gallery_demos()
        return

    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:
        await dbg_simulate_pool_churn(lp_app.deps)


if __name__ == '__main__':
    asyncio.run(main())
