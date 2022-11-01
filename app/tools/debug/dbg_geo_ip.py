import asyncio
import logging
import os
from collections import Counter

from eth_utils.humanize import WEEK

from localization.eng_base import BaseLocalization
from services.dialog.picture.node_geo_picture import node_geo_pic, make_donut_chart
from services.dialog.picture.nodes_pictures import NodePictureGenerator
from services.jobs.fetch.node_info import NodeInfoFetcher
from services.lib.geo_ip import GeoIPManager
from services.lib.utils import setup_logs, load_pickle, save_pickle
from services.models.node_info import NetworkNodeIpInfo
from services.notify.types.node_churn_notify import NodeChurnNotifier
from tools.lib.lp_common import LpAppFramework


async def demo_test_geo_ip_google():
    lp_app = LpAppFramework()
    async with lp_app:
        geo_ip = GeoIPManager(lp_app.deps)

        result = await geo_ip.get_ip_info_from_external_api('8.8.8.8')
        print('Google:', result)
        assert result['org'] == 'GOOGLE'
        assert result['country'] == 'US'


async def get_ip_infos_pickled(path='node_geo_new_full.pickle') -> NetworkNodeIpInfo:
    if path:
        path = os.path.join('../../tmp/', path)
        result_network_info = load_pickle(path)
    else:
        result_network_info = None

    if not result_network_info:
        lp_app = LpAppFramework()
        async with lp_app:
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


async def demo_test_geo_ip_thor_2():
    lp_app = LpAppFramework()
    async with lp_app:
        geo_ip = GeoIPManager(lp_app.deps)

        node_info_fetcher = NodeInfoFetcher(lp_app.deps)
        result = await node_info_fetcher.fetch_current_node_list()

        ip_addresses = [node.ip_address for node in result if node.ip_address]
        print('IP addresses = ')
        print(*ip_addresses, sep=', ')

        ip_infos = await geo_ip.get_ip_info_bulk(ip_addresses)

        organizations = {}
        providers = {}
        for info in ip_infos:
            if info:
                ip = info['ip']
                organizations[ip] = info['org']

        print(organizations)
        print('----')
        print(providers)

        c = Counter(providers.values())
        print(c)

        pic = await node_geo_pic(ip_infos, lp_app.deps.loc_man.default)
        pic.show()


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


async def demo_test_geo_chart():
    infos = await get_ip_infos_pickled()
    pic = await node_geo_pic(infos, BaseLocalization(None))
    pic.show()


async def demo_test_new_geo_chart():
    LpAppFramework.solve_working_dir_mess()

    infos = await get_ip_infos_pickled('nodes_new_3.pickle')
    gen = NodePictureGenerator(infos, BaseLocalization(None))

    pic = await gen.generate()
    pic.show()
    pic.save('../temp/new_node_pic.png')


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
    await demo_test_new_geo_chart()
    # await demo_last_block()
    # await demo_test_parallel_fetch()


if __name__ == "__main__":
    setup_logs(logging.INFO)
    asyncio.run(main())
