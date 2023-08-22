from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger


class LoanExtractorBlock(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
