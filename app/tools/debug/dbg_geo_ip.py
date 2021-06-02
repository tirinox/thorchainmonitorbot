import asyncio
import logging
from collections import Counter

from services.dialog.picture.node_geo_picture import node_geo_pic, make_donut_chart
from services.jobs.fetch.node_info import NodeInfoFetcher
from services.lib.draw_utils import save_image_and_show
from services.lib.geo_ip import GeoIPManager
from services.lib.utils import setup_logs
from tools.lib.lp_common import LpAppFramework


async def test_geo_ip_google():
    lp_app = LpAppFramework()
    async with lp_app:
        geo_ip = GeoIPManager(lp_app.deps)

        result = await geo_ip.get_ip_info_from_external_api('8.8.8.8')
        print('Google:', result)
        assert result['org'] == 'GOOGLE'
        assert result['country'] == 'US'


async def test_geo_ip_thor_2():
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
                providers[ip] = geo_ip.get_general_provider(info)

        print(organizations)
        print('----')
        print(providers)

        c = Counter(providers.values())
        print(c)

        pic = await node_geo_pic(ip_infos)
        pic.show()


async def test_donuts():
    # real_data = [('AMAZON', 24), ('DIGITALOCEAN', 10), ('MICROSOFT', 2), ('Others', 3)]
    fake_data_1 = [('AMAZON', 100), ('DIGITALOCEAN', 50), ('MICROSOFT', 20), ('Others', 1)]
    donut = make_donut_chart(fake_data_1, width=400, margin=104, line_width=60, gap=2, label_r=120)
    donut.show()


async def main():
    # await test_geo_ip_google()
    # await test_geo_ip_thor_2()
    await test_donuts()

if __name__ == "__main__":
    setup_logs(logging.INFO)
    asyncio.run(main())
