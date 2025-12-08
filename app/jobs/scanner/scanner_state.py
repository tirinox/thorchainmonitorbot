import json

from pydantic import BaseModel

from lib.date_utils import now_ts
from lib.db import DB
from lib.logs import WithLogger


class ScannerState(BaseModel):
    role: str = "unknown"
    is_scanning: bool = False
    last_scanned_at_ts: float = 0.0
    started_at_ts: float = 0.0

    last_scanned_block: int = 0
    thor_height_block: int = 0

    total_blocks_scanned: int = 0
    errors_encountered: int = 0

    total_blocks_processed: int = 0

    is_aggressive_mode: bool = False

    total_iterations: int = 0

    avg_block_scanning_time: float = 0.0
    avg_block_processing_time: float = 0.0

    max_block_processing_time: float = 0.0
    max_block_scanning_time: float = 0.0

    last_message: str = ""

    @property
    def success_rate(self) -> float:
        if self.total_blocks_scanned + self.errors_encountered == 0:
            return 0.0
        return self.total_blocks_scanned / (self.total_blocks_scanned + self.errors_encountered) * 100.0

    @property
    def lag_behind_thor(self) -> int:
        if self.thor_height_block == 0:
            return 0
        return self.thor_height_block - self.last_scanned_block


class ScannerStateDB(WithLogger):
    def __init__(self, db: DB, role: str):
        super().__init__()
        self.db = db
        self.role = role

    @property
    def db_key(self) -> str:
        return f'tx:scanner:State:{self.role}'

    async def load_state(self) -> ScannerState:
        r = await self.db.get_redis()
        # load as json
        data = await r.get(self.db_key)
        if not data:
            return ScannerState(role=self.role)
        data_dict = json.loads(data)
        return ScannerState.model_validate(data_dict)

    async def save_state(self, state: ScannerState):
        r = await self.db.get_redis()
        data = state.model_dump()
        await r.set(self.db_key, json.dumps(data))

    async def register(self):
        try:
            state = await self.load_state()
            state.started_at_ts = now_ts()
            state.total_blocks_scanned = 0
            await self.save_state(state)
        except Exception as e:
            self.logger.exception(f'Error registering scanner state: {e}')

    async def set_thor_height(self, thor_block: int):
        try:
            state = await self.load_state()
            if thor_block:
                state.thor_height_block = thor_block
            else:
                state.last_message = "No thor height available"
            await self.save_state(state)
        except Exception as e:
            self.logger.exception(f'Error setting thor height: {e}')

    async def on_new_block_scanned(self, block_number: int, scan_time: float,
                                   is_error: bool = False, message: str = ""):
        try:
            state = await self.load_state()
            state.last_scanned_block = block_number
            state.last_scanned_at_ts = now_ts()
            state.total_blocks_scanned += 1
            # Update average processing time
            n = state.total_blocks_scanned
            state.avg_block_scanning_time = ((state.avg_block_scanning_time * (n - 1)) + scan_time) / n
            state.max_block_scanning_time = max(state.max_block_scanning_time, scan_time)
            if is_error:
                state.errors_encountered += 1
            if message:
                state.last_message = message
            await self.save_state(state)
        except Exception as e:
            self.logger.exception(f'Error updating scanner state on new block: {e}')

    async def on_new_block_processed(self, processing_time: float):
        try:
            state = await self.load_state()
            state.total_blocks_processed += 1
            # Update average processing time
            n = state.total_blocks_processed
            state.avg_block_processing_time = ((state.avg_block_processing_time * (n - 1)) + processing_time) / n
            state.max_block_processing_time = max(state.max_block_processing_time, processing_time)
            await self.save_state(state)
        except Exception as e:
            self.logger.exception(f'Error updating scanner state on new block processed: {e}')

    async def on_iteration_start(self, is_aggressive: bool):
        try:
            state = await self.load_state()
            state.is_aggressive_mode = is_aggressive
            state.is_scanning = True
            state.last_message = "..."
            await self.save_state(state)
        except Exception as e:
            self.logger.exception(f'Error updating scanner state on iteration start: {e}')

    async def on_iteration_end(self):
        try:
            state = await self.load_state()
            state.is_scanning = False
            await self.save_state(state)
        except Exception as e:
            self.logger.exception(f'Error updating scanner state on iteration end: {e}')

    async def set_last_message(self, message: str):
        try:
            state = await self.load_state()
            state.last_message = message
            await self.save_state(state)
        except Exception as e:
            self.logger.exception(f'Error setting last message in scanner state: {e}')
