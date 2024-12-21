from typing import NamedTuple, Dict, List

from jobs.scanner.block_result import BlockResult
from jobs.scanner.tx import NativeThorTx
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.memo import THORMemo
from models.pool_info import PoolInfo


class ThorIntent(NamedTuple):
    pools: Dict[str, PoolInfo]
    memo: THORMemo
    tx: NativeThorTx


class UserIntentDetector(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    async def process_block(self, block: BlockResult) -> List[ThorIntent]:
        return []
