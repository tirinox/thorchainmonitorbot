import asyncio
import logging
import os

from services.jobs.fetch.tx import TxFetcher
from services.jobs.volume_filler import VolumeFillerUpdater
from services.jobs.volume_recorder import VolumeRecorder
from tools.lib.lp_common import LpAppFramework


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app(brief=True):
        fetcher_tx = TxFetcher(lp_app.deps)

        volume_filler = VolumeFillerUpdater(lp_app.deps)
        fetcher_tx.subscribe(volume_filler)

        volume_recorder = VolumeRecorder(lp_app.deps)
        volume_filler.subscribe(volume_recorder)

        await fetcher_tx.run()


if __name__ == '__main__':
    asyncio.run(main())
