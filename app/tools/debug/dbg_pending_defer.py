import asyncio
import logging
from typing import List

from services.jobs.fetch.tx import TxFetcher
from services.jobs.volume_filler import VolumeFillerUpdater
from services.jobs.volume_recorder import VolumeRecorder
from services.lib.date_utils import HOUR
from services.models.tx import ThorTx
from tools.lib.lp_common import LpAppFramework, Receiver


async def continuous_pending_scan(app):
    fetcher_tx = TxFetcher(app.deps)

    volume_filler = VolumeFillerUpdater(app.deps)
    fetcher_tx.add_subscriber(volume_filler)

    pending_set = set()
    block_height = {}

    async def on_data(sender: VolumeRecorder, data: List[ThorTx]):
        for tx in data:
            h = tx.tx_hash
            if h:
                if h in block_height:
                    print(f'Alarm! Block height changed for "{h}"!!!')
                else:
                    block_height[h] = tx.height_int

        succeed = [tx for tx in data if tx.is_success]
        pending = [tx for tx in data if tx.is_pending]
        pending_hashes = {tx.tx_hash for tx in pending}

        pending_set.update(pending_hashes)
        print(f'Pending hashes: {pending_hashes}')
        print(f'{ len(pending) = }, { len(succeed) = }.')

        for tx in succeed:
            h = tx.tx_hash
            if h in pending_set:
                pending.remove(h)
                print(f'Previously pending Tx {h} became Success!')

    volume_filler.add_subscriber(Receiver(callback=on_data))

    await fetcher_tx.run()


async def main():
    app = LpAppFramework(log_level=logging.DEBUG)
    async with app(brief=True):
        await continuous_pending_scan(app)


if __name__ == '__main__':
    asyncio.run(main())
