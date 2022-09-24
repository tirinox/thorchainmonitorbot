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
    fetcher_tx.subscribe(volume_filler)

    async def on_data(sender: VolumeRecorder, data: List[ThorTx]):
        n_success = sum(1 for tx in data if tx.is_success)
        n_pending = sum(1 for tx in data if tx.is_pending)
        print(f'{n_pending = }, {n_success = }.')

    volume_filler.subscribe(Receiver(callback=on_data))

    await fetcher_tx.run()


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app(brief=True):
        await continuous_pending_scan(app)


if __name__ == '__main__':
    asyncio.run(main())
