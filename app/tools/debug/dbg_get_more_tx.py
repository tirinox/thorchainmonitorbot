import asyncio
import json
import logging

import aiohttp

from localization import LocalizationManager
from services.lib.config import Config
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import get_url_gen_by_network_id
from services.models.tx import ThorTxType


async def main(d: DepContainer):
    results = []
    async with aiohttp.ClientSession() as d.session:
        url_gen = get_url_gen_by_network_id(d.cfg.network_id)
        parser = get_parser_by_network_id(d.cfg.network_id)
        offset, batch = 950, 50
        while True:
            url = url_gen.url_for_tx(offset, batch, types=ThorTxType.TYPE_REFUND)
            print(f'Getting {url}...')
            async with d.session.get(url) as resp:
                raw = await resp.json()
                raw_txs = raw['actions']
                txs = parser.parse_tx_response(raw).txs
                if not txs:
                    break

                for raw_tx, tx in zip(raw_txs, txs):
                    if len(tx.in_tx) >= 2 or len(tx.out_tx) >= 2:
                        print(f"{len(tx.in_tx) = }, {len(tx.out_tx) = }")
                        results.append(raw_tx)

                if len(results) > 10:
                    break
            offset += batch

    with open('tests/tx_examples/v2_refund_multi.json', 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.cfg = Config()
    d.loc_man = LocalizationManager(d.cfg)
    d.db = DB(d.loop)

    d.loop.run_until_complete(main(d))
