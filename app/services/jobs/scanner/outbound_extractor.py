from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger


class OutboundExtractorBlock(WithLogger):
    """
    Get L0 outbounds from the block data and pass them to AggregatorAnalytics
    @todo later
    """
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
