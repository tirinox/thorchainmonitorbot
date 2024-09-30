import asyncio
import os

from main import App
from jobs.fetch.base import qualname
from lib.delegates import WithDelegates


class GraphBuilder:
    def __init__(self, tracker: dict):
        self._tracker = tracker

    def make_graph(self):
        results = set()

        queue = set(self._tracker.values())
        root_nodes = set(qualname(node) for node in queue)

        while queue:
            node = queue.pop()
            emitter_name = qualname(node)
            is_root = emitter_name in root_nodes
            if isinstance(node, WithDelegates):
                for listener in node.delegates:
                    listener_name = qualname(listener)
                    results.add((emitter_name, listener_name, is_root))
                    # print((emitter_name, listener_name, is_root))
                    queue.add(listener)

        return results

    @staticmethod
    def make_digraph_dot(list_of_connections):
        dot_code = (
            "digraph G {\n"
            "  layout=fdp;\n"
        )

        def attributed_node(node_name, color=None, is_box=False):
            shape = 'box' if is_box else 'ellipse'
            if color:
                return f'"{node_name}" [fillcolor="{color}"; style="filled"; shape="{shape}"];\n'
            return f'"{node_name}" [shape="{shape}"];\n'

        for edge in list_of_connections:
            node_from, node_to, is_root = edge

            if is_root:
                dot_code += attributed_node(node_from, 'green', is_box=True)
            elif node_to == 'AlertPresenter':
                dot_code += attributed_node(node_to, 'orange')
            elif 'Notifier' in node_to:
                dot_code += attributed_node(node_to, 'yellow')

            dot_code += f'    "{node_from}" -> "{node_to}";\n'

        dot_code += "}"
        return dot_code

    def save_dot_graph(self, filename):
        with open(filename, 'w') as f:
            connections = self.make_graph()
            dot_code = self.make_digraph_dot(connections)
            f.write(dot_code)

    def display_graph(self, out_filename=None):
        filename = '../temp/graph.dot'
        self.save_dot_graph(filename)

        out_filename = out_filename or filename + '.png'
        os.system(f'dot -Tpng "{filename}" > "{out_filename}"')
        os.system(f'open "{out_filename}"')


class GraphApp(App):
    def run_graph(self, out_filename=None):
        asyncio.run(self._run_graph(out_filename))

    async def _run_graph(self, out_filename):
        await self._prepare_task_graph()
        graph_builder = GraphBuilder(self.deps.data_controller.summary)
        graph_builder.display_graph(out_filename)


if __name__ == '__main__':
    GraphApp().run_graph(out_filename='../graph.png')
