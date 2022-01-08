import asyncio

from localization import BaseLocalization
from services.jobs.fetch.tx import merge_affiliate_txs
from services.lib.midgard.connector import MidgardConnector
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import free_url_gen
from services.lib.utils import sep
from services.models.pool_info import PoolInfo
from services.models.tx import ThorTx, ThorTxExtended
from tools.lib.lp_common import LpAppFramework


async def my_test_midgard1():
    lp_app = LpAppFramework()
    async with lp_app:
        await lp_app.prepare(brief=True)
        mdg: MidgardConnector = lp_app.deps.midgard_connector
        tx_parser = get_parser_by_network_id(lp_app.deps.cfg.network_id)

        q_path = free_url_gen.url_for_tx(0, 50,
                                         types='addLiquidity',
                                         txid='58B3D28E121A34BCE2D31018C00C660942088BC548171A427A51F6825ED77142')
        await present_one_aff_tx(lp_app, mdg, q_path, tx_parser)

        q_path = free_url_gen.url_for_tx(0, 50,
                                         types='swap',
                                         txid='7F98B4867018DC97C1DC8A6C34E1E597641FC306093B70AB41F156C85D0CD01E')
        await present_one_aff_tx(lp_app, mdg, q_path, tx_parser)


async def present_one_aff_tx(lp_app, mdg, q_path, tx_parser):
    j = await mdg.request_random_midgard(q_path)
    txs = tx_parser.parse_tx_response(j).txs
    txs_merged = merge_affiliate_txs(txs)
    ex_tx = ThorTxExtended.load_from_thor_tx(txs_merged[0])
    pool_info: PoolInfo = lp_app.deps.price_holder.pool_info_map.get(ex_tx.first_pool)
    asset_per_rune = pool_info.asset_per_rune if pool_info else 0.0
    full_rune = ex_tx.calc_full_rune_amount(asset_per_rune)
    print(f'{ex_tx.affiliate_fee = }')
    rune_price = lp_app.deps.price_holder.usd_per_rune
    print(f'{ex_tx.get_affiliate_fee_usd(rune_price) = } $')
    print(f'{full_rune = } R')
    loc: BaseLocalization = lp_app.deps.loc_man.default
    await lp_app.send_test_tg_message(loc.notification_text_large_tx(ex_tx, rune_price, pool_info))
    sep()


async def main():
    await my_test_midgard1()


if __name__ == '__main__':
    asyncio.run(main())
