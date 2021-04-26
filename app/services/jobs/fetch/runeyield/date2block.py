from services.lib.depcont import DepContainer


class DateToBlockMapper:
    def __init__(self, deps: DepContainer):
        self.deps = deps
