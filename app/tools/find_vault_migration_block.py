import asyncio
import logging

from tools.lib.lp_common import LpAppFramework


async def main(block_start=9867681, block_end=9888681):
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:
        await lp_app.prepare(brief=True)

        thor = lp_app.deps.thor_connector

        if block_end < block_start:
            block_end, block_start = block_start, block_end

        network_end, network_start = await asyncio.gather(
            thor.query_network(block_end),
            thor.query_network(block_start),
        )

        assert network_end and not network_end.vaults_migrating
        assert network_start and network_start.vaults_migrating

        while abs(block_end - block_start) > 1:
            print(f'Range is {block_start} - {block_end}')
            middle = (block_start + block_end) // 2
            middle_network = await thor.query_network(middle)
            if middle_network.vaults_migrating:
                block_start = middle
            else:
                block_end = middle

        print(f'vaults_migrating became False at block #{block_end}')


asyncio.run(main())
