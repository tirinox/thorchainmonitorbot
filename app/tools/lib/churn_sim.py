import random

from services.lib.delegates import WithDelegates, INotified
from services.lib.texts import sep
from services.models.node_info import NodeSetChanges, NodeInfo


class DbgChurnSimulator(WithDelegates, INotified):
    def __init__(self, trigger_on_tick, every_tick=True):
        super().__init__()
        self.counter = 1
        self.trigger_on_tick = trigger_on_tick
        self.every_tick = every_tick

    async def on_data(self, sender, data: NodeSetChanges):

        if self.counter == self.trigger_on_tick or (self.every_tick and self.counter % self.trigger_on_tick == 0):
            sep('Simulating node churn')
            self.simulate_churn(data)
            print(data)

        await self.pass_data_to_listeners(data)
        self.counter += 1

    @staticmethod
    def simulate_churn(nodes: NodeSetChanges):
        active_nodes = nodes.active_only_nodes
        standby_nodes = [n for n in nodes.nodes_all if n.is_standby]
        deactivate = random.sample(active_nodes, random.randint(1, 5))
        activate = random.sample(standby_nodes, random.randint(1, 5))
        for n in activate:
            n: NodeInfo
            n.status = n.ACTIVE
            nodes.nodes_activated.append(n)
        for n in deactivate:
            n.status = n.STANDBY
            nodes.nodes_deactivated.append(n)
