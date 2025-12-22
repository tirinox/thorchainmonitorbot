import asyncio
import time
from contextlib import suppress
from typing import Optional

from jobs.fetch.base import BaseFetcher
from jobs.scanner.block_result import BlockResult
from jobs.scanner.scanner_state import ScannerStateDB
from lib.constants import THOR_BLOCK_TIME
from lib.date_utils import now_ts
from lib.depcont import DepContainer
from lib.utils import safe_get


class BlockScanner(BaseFetcher):
    MAX_ATTEMPTS_TO_SKIP_BLOCK = 5

    NAME = 'block_scanner'

    def __init__(self, deps: DepContainer, sleep_period=None, last_block=0, max_attempts=MAX_ATTEMPTS_TO_SKIP_BLOCK,
                 role='secondary'):
        sleep_period = sleep_period or THOR_BLOCK_TIME * 0.99
        super().__init__(deps, sleep_period)
        self._last_block = last_block
        self._this_block_attempts = 0
        self.max_attempts = max_attempts
        self.one_block_per_run = False
        self.allow_jumps = True
        self._block_cycle = 0
        self._last_block_ts = 0
        self.role = role
        self.state_db = ScannerStateDB(deps.db, role)

        # if more time has passed since the last block, we should run aggressive scan
        self._time_tolerance_for_aggressive_scan = THOR_BLOCK_TIME * 1.5  # 6 sec + 50%

    @property
    def last_block_ts(self):
        return self._last_block_ts

    @property
    def block_cycle(self):
        return self._block_cycle

    @property
    def last_block(self):
        return self._last_block

    @last_block.setter
    def last_block(self, value):
        self.logger.warning(f'Last block number manually changed from {self._last_block} to {value}.')
        self._last_block = value

    def _on_error(self, reason='', **kwargs):
        self.logger.warning(f'Error fetching block #{self._last_block} ({reason = !r}).')
        self._this_block_attempts += 1
        if self._this_block_attempts >= self.max_attempts:
            self.logger.error(f'Too many attempts to get block #{self._last_block}. Skipping it.')
            self.deps.emergency.report(self.NAME, 'Block scan fail',
                                       block_no=self._last_block,
                                       **kwargs)

            self._last_block += 1
            self._this_block_attempts = 0

    async def ensure_last_block(self, reset=False):
        if reset:
            self._last_block = 0
        while not self._last_block:
            last_block = await self._fetch_last_block()
            last_thor_block = 0  # reset to avoid multiple calls
            if last_block:
                self._last_block = last_block
                self.logger.info(f'Updated last block number: #{self._last_block}')
            else:
                self.logger.error('Still no last_block height!')
                await asyncio.sleep(self.sleep_period)

    async def _refresh_thor_block_for_state(self):
        with suppress(Exception):
            last_thor_block = await self._fetch_last_block()
            if last_thor_block:
                await self.state_db.set_thor_height(last_thor_block)

    def _on_error_block(self, block: BlockResult):
        self._on_error(f'Block.error #{block.error.code}: {block.error.message}',
                       code=block.error.code,
                       message=block.error.message,
                       last_available=block.error.last_available_block)

    async def should_run_aggressive_scan(self):
        time_since_last_block = now_ts() - self._last_block_ts
        if time_since_last_block > self._time_tolerance_for_aggressive_scan:
            self.logger.info(f'😡 time_since_last_block = {time_since_last_block:.3f} sec. Run aggressive scan!')
            return True

        last_block = await self.deps.last_block_cache.get_thor_block()
        lag_behind_node_block = last_block - self._last_block
        if lag_behind_node_block > 2:
            self.logger.info(f"😡 {lag_behind_node_block = }. Run aggressive scan!")
            return True

        return False

    async def run(self):
        await self.state_db.register()
        return await super().run()

    async def fetch(self):
        await self.ensure_last_block()

        if self._last_block % 10 == 0:
            self.logger.info(f'👿 Tick start for block #{self._last_block}.')
        else:
            self.logger.debug(f'👿 Tick start for block #{self._last_block}.')

        self._block_cycle = 0

        aggressive = await self.should_run_aggressive_scan()
        if aggressive:
            self.logger.info('Aggressive scan will be run at this tick.')
        await self.state_db.on_iteration_start(aggressive)

        while True:
            try:
                asyncio.create_task(self._refresh_thor_block_for_state())
                self.logger.info(f'Fetching block #{self._last_block}. Cycle: {self._block_cycle}.')
                start_ts = time.monotonic()
                block_result = await self.fetch_one_block(self._last_block)
                end_ts = time.monotonic()

                if block_result is None:
                    self._on_error('None returned')
                    await self.state_db.on_new_block_scanned(self._last_block, end_ts - start_ts, is_error=True,
                                                             message='No block data returned')
                    break

                await self.state_db.on_new_block_scanned(self._last_block, end_ts - start_ts)

                # if block_result.timestamp:
                #     self._last_block_ts = block_result.timestamp
                self._last_block_ts = now_ts()

                if block_result.is_error:
                    if self.allow_jumps:
                        last_av_b = block_result.error.last_available_block
                        if block_result.is_behind:
                            self.logger.warning(f'It seems that no blocks available before '
                                                f'{last_av_b}. '
                                                f'Jumping to it!')
                            self.deps.emergency.report(self.NAME, 'Jump block',
                                                       from_block=self._last_block,
                                                       to_block=last_av_b)
                            self._last_block = last_av_b
                            self._this_block_attempts = 0
                        elif block_result.is_ahead:
                            self.logger.warning(f'We are running ahead of real block height. '
                                                f'{self._last_block = },'
                                                f'{last_av_b = }')
                            await self.ensure_last_block(reset=True)
                            break
                        else:
                            self._on_error_block(block_result)
                            break
                    else:
                        self._on_error_block(block_result)
                        break

            except Exception as e:
                self.logger.exception(f'Error while fetching block #{self._last_block}: {e}')
                self._on_error(str(e))
                await self.state_db.on_new_block_scanned(self._last_block, 0, is_error=True,
                                                         message=str(e))
                break

            self._last_block += 1
            self._this_block_attempts = 0
            self._block_cycle += 1

            start_ts = time.monotonic()
            await self.pass_data_to_listeners(block_result)
            end_ts = time.monotonic()
            await self.state_db.on_new_block_processed(end_ts - start_ts)

            if self.one_block_per_run:
                self.logger.warning('One block per run mode is on. Stopping.')
                break

            if not aggressive:
                # only one block at the time if it is not aggressive scan
                break

        await self.state_db.on_iteration_end()

    async def _fetch_last_block(self):
        result = await self.deps.thor_connector.query_native_status_raw()
        if result:
            return int(safe_get(result, 'result', 'sync_info', 'latest_block_height'))
        else:
            return None

    async def _fetch_raw_block(self, block_no):
        return await self.deps.thor_connector.query_thorchain_block_raw(block_no)

    async def fetch_one_block(self, block_index) -> Optional[BlockResult]:
        block_raw = await self._fetch_raw_block(block_index)
        if block_raw is None:
            return None

        block_result = BlockResult.load_block(block_raw, block_index)

        if block_result.is_error:
            return block_result

        self.logger.info(
            f'Block #{block_index} has {len(block_result.txs)} txs, '
            f'{len(block_result.end_block_events)} end block events, '
            f'{len(block_result.begin_block_events)} begin block events.'
        )

        # So we match the logs with the txs
        return block_result.only_successful
