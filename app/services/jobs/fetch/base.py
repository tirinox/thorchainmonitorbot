import asyncio
import datetime
import os
import random
import time
from abc import ABC, abstractmethod
from collections import deque
from typing import Dict

from services.lib.date_utils import now_ts
from services.lib.delegates import WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger


class WatchedEntity:
    def __init__(self):
        super().__init__()
        self.name = self.__class__.__qualname__
        self.sleep_period = 1.0
        self.initial_sleep = 1.0
        self.last_timestamp = 0.0
        self.error_counter = 0
        self.total_ticks = 0
        self.creating_date = now_ts()

    @property
    def success_rate(self):
        if not self.total_ticks:
            return 100.0
        return (self.total_ticks - self.error_counter) / self.total_ticks * 100.0


def qualname(obj):
    if hasattr(obj, '__qualname__'):
        return obj.__qualname__
    return obj.__class__.__qualname__


class DataController:
    def __init__(self):
        self._tracker = {}

    def register(self, entity: WatchedEntity):
        if not entity:
            return
        name = entity.name
        self._tracker[name] = entity

    def unregister(self, entity):
        if not entity:
            return
        self._tracker.pop(entity.name)

    @property
    def summary(self) -> Dict[str, WatchedEntity]:
        return self._tracker

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
                    queue.add(listener)

        return results

    @staticmethod
    def make_digraph_dot(list_of_connections):
        dot_code = (
            "digraph G {\n"
            "  layout=fdp;\n"
        )

        for edge in list_of_connections:
            node_from, node_to, is_root = edge
            if is_root:
                color = 'green' if is_root else 'black'
                dot_code += f'    "{node_from}" [fillcolor="{color}"; style="filled"; shape="box"];\n'
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


class BaseFetcher(WithDelegates, WatchedEntity, ABC, WithLogger):
    MAX_STARTUP_DELAY = 60

    def __init__(self, deps: DepContainer, sleep_period=60):
        super().__init__()
        self.deps = deps

        self.sleep_period = sleep_period
        self.initial_sleep = random.uniform(0, min(self.MAX_STARTUP_DELAY, sleep_period))
        self.data_controller.register(self)
        self.run_times = deque(maxlen=100)

    @property
    def dbg_last_run_time(self):
        return self.run_times[-1] if self.run_times else None

    @property
    def dbg_average_run_time(self):
        return sum(self.run_times) / len(self.run_times) if self.run_times else None

    @property
    def data_controller(self):
        if not self.deps.data_controller:
            self.deps.data_controller = DataController()
        return self.deps.data_controller

    async def post_action(self, data):
        ...

    @abstractmethod
    async def fetch(self):
        ...

    async def run_once(self):
        self.logger.info(f'Tick #{self.total_ticks}')
        t0 = time.monotonic()
        try:
            data = await self.fetch()
            await self.pass_data_to_listeners(data)
            await self.post_action(data)
        except Exception as e:
            self.logger.exception(f"task error: {e}")
            self.error_counter += 1
            try:
                await self.handle_error(e)
            except Exception as e:
                self.logger.exception(f"task error while handling on_error: {e}")
        finally:
            self.total_ticks += 1
            self.last_timestamp = datetime.datetime.now().timestamp()
            delta = time.monotonic() - t0
            self.run_times.append(delta)

    async def _run(self):
        if self.sleep_period < 0:
            self.logger.info('This fetcher is disabled.')
            return

        self.logger.info(f'Waiting {self.initial_sleep:.1f} sec before starting this fetcher...')
        await asyncio.sleep(self.initial_sleep)
        self.logger.info(f'Starting this fetcher with period {self.sleep_period:.1f} sec.')

        while True:
            await self.run_once()
            await asyncio.sleep(self.sleep_period)

    async def run(self):
        try:
            await self._run()
        except Exception as e:
            self.logger.error(f'Unexpected termination due to exception {e!r}')
        finally:
            self.logger.warning('Unexpected termination!')

    def run_in_background(self):
        asyncio.create_task(self.run())
