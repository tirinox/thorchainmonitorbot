import asyncio

import aiohttp

from main import App


class ConsensusTestApp(App):
    async def main(self):
        self.deps.session = aiohttp.ClientSession()
        await self.create_thor_node_connector()
        await self.deps.session.close()


if __name__ == '__main__':
    app = ConsensusTestApp()
    asyncio.run(app.main())
