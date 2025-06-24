import asyncio
import sys

import aiohttp
import yaml

from lib.texts import sep

# This is not list of affiliates, please see: app/data/affiliates.yaml !
name_to_code = {
    'trustwallet': 'trust',
    'trust': '',
    'thorswap': '',
    'asgardex': '',
    'babylonswap': '',
    'bitget': '',
    'cacaoswap': '',
    'cakewallet': '',
    'coinbot': '',

    'ctrl': '',
    'xdefi': 'ctrl',

    'decentralfi': '',
    'edgewallet': '',
    'eldorito': '',
    'ethos': '',
    'gemwallet': '',
    'giddy': '',
    'instaswap': '',

    'ledgerlive': '',
    'ledger live': 'ledgerlive',
    'ledger': 'ledgerlive',
    'll': 'ledgerlive',

    'lends': '',
    'lifi': '',
    'li.fi': 'lifi',
    'okx': '',
    'onekey': '',
    'rango': '',
    'shapeshift': '',
    'symbiosis': '',
    'thorwallet': '',
    'unizen': '',
    'vultisig': '',
    'vultisig ios': 'vultisig',
    'vultisig android': 'vultisig',

    'zengo': '',
    'tokenpocket': '',
    'swapkit': '',
}


async def probe_url_exists(session, url):
    async with session.head(url) as response:
        return response.status == 200


async def main():
    results = {}
    async with aiohttp.ClientSession() as session:
        base_url = "https://raw.githubusercontent.com/ViewBlock/cryptometa/master/data/thorchain/ecosystem/{name}/logo.{ext}"
        for k, v in name_to_code.items():
            sep(k)
            if v == '':
                v = k
            url_png = base_url.format(name=v, ext='png')
            url_svg = base_url.format(name=v, ext='svg')

            if await probe_url_exists(session, url_png):
                print(f"PNG exists: {url_png}")
                results[v] = url_png
            elif await probe_url_exists(session, url_svg):
                print(f"SVG exists: {url_svg}")
                results[v] = url_svg
            else:
                print(f"Neither PNG nor SVG exists for {k} ({v})")

    yaml.dump(results, sys.stdout)


if __name__ == '__main__':
    asyncio.run(main())
