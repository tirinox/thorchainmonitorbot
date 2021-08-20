from services.jobs.fetch.base import INotified


class NodeChangePersonalNotifier(INotified):
    async def on_data(self, sender, data):
        pass