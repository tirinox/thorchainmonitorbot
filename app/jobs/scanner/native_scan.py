import asyncio
from typing import Optional

from jobs.fetch.base import BaseFetcher
from jobs.scanner.block_result import BlockResult
from lib.constants import THOR_BLOCK_TIME
from lib.date_utils import now_ts_utc
from lib.depcont import DepContainer
from lib.utils import safe_get


class BlockScanner(BaseFetcher):
    MAX_ATTEMPTS_TO_SKIP_BLOCK = 5

    NAME = 'block_scanner'

    def __init__(self, deps: DepContainer, sleep_period=None, last_block=0, max_attempts=MAX_ATTEMPTS_TO_SKIP_BLOCK):
        sleep_period = sleep_period or THOR_BLOCK_TIME * 0.99
        super().__init__(deps, sleep_period)
        self._last_block = last_block
        self._this_block_attempts = 0
        self.max_attempts = max_attempts
        self.one_block_per_run = False
        self.allow_jumps = True
        self._block_cycle = 0
        self._last_block_ts = 0

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

    async def ensure_last_block(self):
        while not self._last_block:
            last_block = await self._fetch_last_block()
            if last_block:
                self._last_block = last_block
                self.logger.info(f'Updated last block number: #{self._last_block}')
            else:
                self.logger.error('Still no last_block height!')
                await asyncio.sleep(self.sleep_period)

    async def check_lagging(self):
        # todo: use it!
        real_last_block = await self._fetch_last_block()
        if not real_last_block:
            self.logger.error('Failed to get real last block number!')
            return False
        delta = real_last_block - self._last_block
        if delta > 10:
            self.logger.warning(f'Lagging behind {delta} blocks!')
            self.deps.emergency.report(self.NAME, 'Lagging behind',
                                       delta=delta,
                                       my_block=self._last_block,
                                       real_block=real_last_block)
            return False

    def _on_error_block(self, block: BlockResult):
        self._on_error(f'Block.error #{block.error.code}: {block.error.message}',
                       code=block.error.code,
                       message=block.error.message,
                       last_available=block.error.last_available_block)

    def should_run_aggressive_scan(self):
        time_since_last_block = now_ts_utc() - self._last_block_ts
        if time_since_last_block > self._time_tolerance_for_aggressive_scan:
            self.logger.info(f'😡 time_since_last_block = {time_since_last_block:.3f} sec. Run aggressive scan!')
            return True

        lag_behind_node_block = int(self.deps.last_block_store) - self._last_block
        if lag_behind_node_block > 2:
            self.logger.info(f"😡 {lag_behind_node_block = }. Run aggressive scan!")
            return True

        return False

    async def fetch(self):
        await self.ensure_last_block()

        if self._last_block % 10 == 0:
            self.logger.info(f'👿 Tick start for block #{self._last_block}.')
        else:
            self.logger.debug(f'👿 Tick start for block #{self._last_block}.')

        self._block_cycle = 0

        aggressive = self.should_run_aggressive_scan()
        if aggressive:
            self.logger.info('Aggressive scan will be run at this tick.')

        while True:
            try:
                self.logger.info(f'Fetching block #{self._last_block}. Cycle: {self._block_cycle}.')
                block_result = await self.fetch_one_block(self._last_block)

                if block_result is None:
                    self._on_error('None returned')
                    break

                # if block_result.timestamp:
                #     self._last_block_ts = block_result.timestamp
                self._last_block_ts = now_ts_utc()

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
                            self.logger.debug(f'We are running ahead of real block height. '
                                              f'{self._last_block = },'
                                              f'{last_av_b = }')
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
                break

            self._last_block += 1
            self._this_block_attempts = 0
            self._block_cycle += 1

            await self.pass_data_to_listeners(block_result)

            if self.one_block_per_run:
                self.logger.warning('One block per run mode is on. Stopping.')
                break

            if not aggressive:
                # only one block at the time if it is not aggressive scan
                break

    async def _fetch_last_block(self):
        result = await self.deps.thor_connector.query_native_status_raw()
        if result:
            return int(safe_get(result, 'result', 'sync_info', 'latest_block_height'))

    async def fetch_one_block(self, block_index) -> Optional[BlockResult]:
        block_raw = await self.deps.thor_connector.query_thorchain_block_raw(block_index)
        if block_raw is None:
            return

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
