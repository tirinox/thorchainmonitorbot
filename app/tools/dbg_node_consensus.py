import asyncio

import aiohttp

from main import App
from services.fetch.thor_node import ThorNode


class ConsensusTestApp(App):
    async def main(self):
        d = self.deps
        d.session = aiohttp.ClientSession()
        await self.create_thor_node_connector()

        thor: ThorNode = d.thor_nodes

        results = await thor.request('/thorchain/queue')
        print(results)

        await d.session.close()


if __name__ == '__main__':
    app = ConsensusTestApp()
    asyncio.run(app.main())
