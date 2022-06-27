from aiothornode.nodeclient import ThorNodePublicClient

from proto import NativeThorTx
from services.jobs.fetch.base import BaseFetcher
from services.lib.depcont import DepContainer
from services.lib.utils import safe_get


class NativeScannerBlock(BaseFetcher):
    SLEEP_PERIOD = 5.99

    def __init__(self, deps: DepContainer):
        super().__init__(deps, self.SLEEP_PERIOD)
        self._last_block = 0
        self._thor = ThorNodePublicClient(self.deps.session, self.deps.thor_env)

    async def _update_last_block(self):
        result = await self._thor.request('/status?', is_rpc=True)
        if result:
            self._last_block = int(safe_get(result, 'result', 'sync_info', 'latest_block_height'))
            self.logger.info(f'Updated last block: #{self._last_block}')

    async def fetch(self):
        if not self._last_block:
            await self._update_last_block()

        if not self._last_block:
            return

        result = await self.deps.thor_connector.query_tendermint_block_raw(self._last_block)
        if result:
            self._last_block += 1

            raw_txs = safe_get(result, 'result', 'block', 'data', 'txs')
            txs = [NativeThorTx.from_base64(raw) for raw in raw_txs]
            await self.pass_data_to_listeners(txs)
        else:
            self.logger.warning(f'Yet no block: #{self._last_block}. I will try on the next tick...')
