import asyncio
import os
import random

from eth_utils.humanize import WEEK

from comm.picture.nodes_pictures import NodePictureGenerator
from jobs.fetch.node_info import NodeInfoFetcher
from lib.date_utils import now_ts, DAY, HOUR
from lib.draw_utils import make_donut_chart
from lib.geo_ip import GeoIPManager
from lib.utils import load_pickle, save_pickle
from models.node_info import NetworkNodeIpInfo, NodeStatsItem
from notify.public.node_churn_notify import NodeChurnNotifier
from tools.lib.lp_common import LpAppFramework, save_and_show_pic


async def demo_test_geo_ip_google():
    lp_app = LpAppFramework()
    async with lp_app:
        geo_ip = GeoIPManager(lp_app.deps)

        result = await geo_ip.get_ip_info_from_external_api('8.8.8.8')
        print('Google:', result)
        assert result['org'] == 'GOOGLE'
        assert result['country'] == 'US'


async def get_ip_infos_pickled(lp_app, path='node_geo_new_full.pickle') -> NetworkNodeIpInfo:
    if path:
        path = os.path.join('../../tmp/', path)
        result_network_info = load_pickle(path)
    else:
        result_network_info = None

    if not result_network_info:
        geo_ip = GeoIPManager(lp_app.deps)

        node_info_fetcher = NodeInfoFetcher(lp_app.deps)
        node_list = await node_info_fetcher.fetch_current_node_list()

        ip_addresses = [node.ip_address for node in node_list if node.ip_address]
        print('IP addresses = ')
        print(*ip_addresses, sep=', ')

        ip_info_list = await geo_ip.get_ip_info_bulk(ip_addresses)
        ip_info_dict = {n["ip"]: n for n in ip_info_list if n and 'ip' in n}

        result_network_info = NetworkNodeIpInfo(
            node_list,
            ip_info_dict
        )

        if result_network_info and path:
            save_pickle(path, result_network_info)
    return result_network_info


async def demo_get_node_stats():
    lp_app = LpAppFramework()
    async with lp_app:
        obj = NodeChurnNotifier(lp_app.deps)
        r = await obj.load_last_statistics(WEEK * 2)
        print(r)


async def demo_test_parallel_fetch():
    lp_app = LpAppFramework()
    async with lp_app:
        geo_ip = GeoIPManager(lp_app.deps)

        node_info_fetcher = NodeInfoFetcher(lp_app.deps)
        result = await node_info_fetcher.fetch_current_node_list()

        ip_addresses = [node.ip_address for node in result if node.ip_address]

        for ip in ip_addresses:
            await geo_ip.clear_info(ip)

        print('IP addresses = ')
        print(*ip_addresses, sep=', ')

        ip_infos = await geo_ip.get_ip_info_bulk(ip_addresses)
        print(ip_infos)


async def demo_test_donuts():
    # real_data = [('AMAZON', 24), ('DIGITALOCEAN', 10), ('MICROSOFT', 2), ('Others', 3)]
    fake_data_1 = [('AMAZON', 100), ('DIGITALOCEAN', 50), ('MICROSOFT', 20), ('Others', 1)]
    donut = make_donut_chart(fake_data_1, width=400, margin=104, line_width=60, gap=2, label_r=120)
    donut.show()


def dbg_bond_stat_entry(day, shift, nodes_active, bond_millions):
    ts = now_ts() - day * DAY - shift
    return NodeStatsItem(ts, 0, 100, 1000, bond_millions, bond_millions, nodes_active, nodes_active)


EXAMPLE_CHAR_PTS = [
    dbg_bond_stat_entry(0, 1 * HOUR, 65, 88),
    dbg_bond_stat_entry(1, 2 * HOUR, 65, 88),
    dbg_bond_stat_entry(2, 0 * HOUR, 65, 88),
    dbg_bond_stat_entry(3, 3 * HOUR, 65, 88),
    dbg_bond_stat_entry(4, 2 * HOUR, 62, 75),
    dbg_bond_stat_entry(5, 3 * HOUR, 62, 75),
    # gap!
    dbg_bond_stat_entry(10, 4 * HOUR, 60, 69),
    dbg_bond_stat_entry(11, 1 * HOUR, 60, 69),
    dbg_bond_stat_entry(12, 3 * HOUR, 60, 68),
    dbg_bond_stat_entry(13, 0 * HOUR, 60, 68),
    # gap 1d
    dbg_bond_stat_entry(15, 0 * HOUR, 66, 71),
    dbg_bond_stat_entry(16, 1 * HOUR, 66, 71),
    dbg_bond_stat_entry(17, 0 * HOUR, 64, 70),
    dbg_bond_stat_entry(18, 0 * HOUR, 64, 70),
]


def make_random_node_chart(days=31, reverse=True):
    r = range(days)
    n = 85
    bond = 70e6
    for day in (reversed(r) if reverse else r):
        yield dbg_bond_stat_entry(day, random.uniform(-HOUR, HOUR), n, bond)
        if day % 3 == 0:
            n += random.randint(-5, 5)
            bond *= random.uniform(0.8, 1.2)


async def demo_test_new_geo_chart(app: LpAppFramework):
    LpAppFramework.solve_working_dir_mess()

    chart_pts = await NodeChurnNotifier(app.deps).load_last_statistics(NodePictureGenerator.CHART_PERIOD)
    # chart_pts = EXAMPLE_CHAR_PTS
    # chart_pts = EXAMPLE_CHAR_PTS[5:7]
    # chart_pts = list(make_random_node_chart())

    # infos = await get_ip_infos_pickled(app, 'nodes_new_10.pickle')
    infos = await get_ip_infos_pickled(app, path=None)
    gen = NodePictureGenerator(infos, chart_pts, app.deps.loc_man.default)

    pic = await gen.generate()

    save_and_show_pic(pic, name='new_node_pic.png')

    # usage
    """
    node_set_info: NetworkNodeIpInfo
    churn_notifier: NodeChurnNotifier
    loc: BaseLocalisation
    chart_pts = await churn_notifier.load_last_statistics(NodePictureGenerator.CHART_PERIOD)
    gen = NodePictureGenerator(node_set_info, chart_pts, loc)
    pic = await gen.generate()
    """


async def demo_last_block():
    lp_app = LpAppFramework()
    async with lp_app:
        r = await lp_app.deps.thor_connector.query_last_blocks()
        print(r)


async def main():
    # await test_geo_ip_google()
    # await test_geo_ip_thor_2()
    # await test_donuts()
    # await demo_get_node_stats()
    await demo_test_parallel_fetch()
    # lp_app = LpAppFramework()
    # async with lp_app:
    #     # await demo_test_new_geo_chart(lp_app)
    #     # await demo_last_block()
    #     await demo_test_parallel_fetch()


if __name__ == "__main__":
    asyncio.run(main())
