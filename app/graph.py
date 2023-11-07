import asyncio

from main import App
from services.jobs.fetch.base import GraphBuilder


class GraphApp(App):
    def run_graph(self, out_filename=None):
        asyncio.run(self._run_graph(out_filename))

    async def _run_graph(self, out_filename):
        await self._prepare_task_graph()
        graph_builder = GraphBuilder(self.deps.data_controller.summary)
        graph_builder.display_graph(out_filename)


if __name__ == '__main__':
    GraphApp().run_graph(out_filename='../graph.png')
