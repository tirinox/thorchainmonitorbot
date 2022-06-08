from services.jobs.fetch.base import BaseFetcher
from services.lib.constants import BNB_RUNE_SYMBOL_NO_CHAIN
from services.lib.date_utils import parse_timespan_to_seconds, now_ts
from services.lib.delegates import WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import run_once_async
from services.lib.web_sockets import WSClient
from services.models.bep2 import BEP2Transfer

BEP2_BLOCK_URL = 'https://api.binance.org/bc/api/v1/blocks/{block}/txs'


class BEP2BlockFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.bep2.fetch_period)
        super().__init__(deps, sleep_period)

    async def get_block(self, block_number):
        url = BEP2_BLOCK_URL.format(block=block_number)
        async with self.deps.session.get(url) as resp:
            return await resp.json()

    async def fetch(self):
        return 1


BEP2_DEX_WSS_ADDRESS = 'wss://explorer.bnbchain.org/ws/tx'
BEP2_DEX_ORIGIN = 'https://explorer.binance.org/'
BEP2_TRANSFER = 'TRANSFER'


class BinanceOrgDexWSSClient(WSClient, WithDelegates):
    def __init__(self, reply_timeout=10, ping_timeout=5, sleep_time=5):
        headers = {
            # 'Origin': BEP2_DEX_ORIGIN,
            'Sec-WebSocket-Extensions': 'permessage-deflate; client_max_window_bits',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'User-Agent': ''
        }
        self.last_message_ts = 0.0

        super().__init__(BEP2_DEX_WSS_ADDRESS, reply_timeout, ping_timeout, sleep_time, headers=headers)

    @property
    def last_signal_sec_ago(self):
        return now_ts() - self.last_message_ts

    async def handle_wss_message(self, j):
        # await self._dbg_later()

        for tx in j:
            if tx.get('txType') == BEP2_TRANSFER and tx.get('txAsset') == BNB_RUNE_SYMBOL_NO_CHAIN:
                self.logger.info(f'Transfer message: {tx}')
                await self.pass_data_to_listeners(BEP2Transfer(
                    tx.get('fromAddr'),
                    tx.get('toAddr'),
                    tx.get('blockHeight'),
                    tx.get('txHash'),
                    tx.get('value'),
                ))

    async def on_connected(self):
        self.logger.info('Connected to Binance.org.')

    @run_once_async
    async def _dbg_later(self):
        await self.pass_data_to_listeners(BEP2Transfer(
            'bnb1u2agwjat20494fmc6jnuau0ls937cfjn4pjwtn',
            'bnb13q87ekxvvte78t2q7z05lzfethnlht5agfh4ok',
            # 'bnb13q87ekxvvte78t2q7z05lzfethnlht5agfh4ur',
            10000,
            '12345',
            4310.0,
            5.5,
        ))
