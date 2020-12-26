import asyncio

import aiohttp

from main import App
from services.fetch.queue import QueueFetcher


class ConsensusTestApp(App):
    async def main(self):
        d = self.deps
        d.session = aiohttp.ClientSession()
        await self.create_thor_node_connector()

        fetcher = QueueFetcher(d)
        print(await fetcher.fetch())

        await d.session.close()


if __name__ == '__main__':
    app = ConsensusTestApp()
    asyncio.run(app.main())
