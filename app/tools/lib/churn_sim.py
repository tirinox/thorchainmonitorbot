import random

from services.jobs.node_churn import NodeChurnDetector
from services.lib.delegates import WithDelegates, INotified
from services.lib.depcont import DepContainer
from services.lib.texts import sep
from services.models.node_info import NodeSetChanges, NodeInfo


class DbgChurnSimulator(WithDelegates, INotified):
    def __init__(self, deps: DepContainer, trigger_on_tick, every_tick=True, tick_duration=10):
        super().__init__()
        self.deps = deps
        self.counter = 1
        self.trigger_on_tick = trigger_on_tick
        self.every_tick = every_tick
        self.tick_duration = tick_duration

        self.node_churn_detector = NodeChurnDetector(deps)

        self.vaults_migrating = False

        self.min_activate_number = 1
        self.max_activate_number = 5
        self.min_deactivate_number = 1
        self.max_deactivate_number = 5

    async def run_standalone(self):
        # node_info_fetcher -> node_churn_detector -> self -> ...
        self.deps.node_info_fetcher.add_subscriber(self.node_churn_detector)

        self.node_churn_detector.add_subscriber(self)

        self.deps.node_info_fetcher.sleep_period = self.tick_duration
        self.deps.node_info_fetcher.initial_sleep = 0
        await self.deps.node_info_fetcher.run()

    def toggle_migration(self, data: NodeSetChanges, in_progress: bool):
        self.vaults_migrating = in_progress
        data.vault_migrating = in_progress
        if self.vaults_migrating:
            sep('🍯Node churn: vaults migration started')
            self.simulate_churn(data)
            print(data)
        else:
            sep('Vaults migration finished')

        print(f'🏛️Vaults migration: {self.vaults_migrating}')

        return data

    async def on_data(self, sender, data: NodeSetChanges):
        print(f'  >> Churn sim >> tick >> #{self.counter}')

        if self.vaults_migrating:
            self.toggle_migration(data, in_progress=False)  # finish
        elif self.counter == self.trigger_on_tick or (self.every_tick and self.counter % self.trigger_on_tick == 0):
            self.toggle_migration(data, in_progress=True)  # start

        await self.pass_data_to_listeners(data)
        self.counter += 1

    def simulate_churn(self, nodes: NodeSetChanges):
        active_nodes = nodes.active_only_nodes
        standby_nodes = [n for n in nodes.nodes_all if n.is_standby]
        deactivate = random.sample(active_nodes, random.randint(self.min_deactivate_number, self.max_deactivate_number))
        activate = random.sample(standby_nodes, random.randint(self.min_activate_number, self.max_activate_number))
        for n in activate:
            n: NodeInfo
            n.status = n.ACTIVE
            nodes.nodes_activated.append(n)
        for n in deactivate:
            n.status = n.STANDBY
            nodes.nodes_deactivated.append(n)
