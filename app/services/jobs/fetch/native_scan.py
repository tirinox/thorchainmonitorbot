import json
from urllib.parse import urlparse, urlunparse

from proto import NativeThorTx, thor_decode_event
from services.lib.delegates import WithDelegates
from services.lib.utils import safe_get
from services.lib.web_sockets import WSClient


class NativeScanner(WSClient, WithDelegates):
    REPLY_TIMEOUT = 20
    PING_TIMEOUT = 6
    SLEEP_TIME = 6

    def __init__(self, node_rpc_url):
        parsed = urlparse(node_rpc_url)
        wss_scheme = 'wss' if parsed.scheme == 'https' else 'ws'

        # make WebSocketURL
        wss_url = urlunparse((
            # scheme netloc path params query fragment
            wss_scheme, parsed.netloc, 'websocket', '', '', ''
        ))

        super().__init__(wss_url,
                         reply_timeout=self.REPLY_TIMEOUT,
                         ping_timeout=self.PING_TIMEOUT,
                         sleep_time=self.SLEEP_TIME)

    async def handle_wss_message(self, reply: dict):
        pass


class NativeScannerBlockEvents(NativeScanner):
    SUBSCRIBE_NEW_BLOCK = {"jsonrpc": "2.0", "method": "subscribe", "params": ["tm.event='NewBlock'"], "id": 1}

    async def on_connected(self):
        self.logger.info('Connected, subscribing to new data...')
        await self.ws.send(json.dumps(self.SUBSCRIBE_NEW_BLOCK))

    async def handle_wss_message(self, reply: dict):
        block_events = safe_get(reply, 'result', 'data', 'value', 'result_end_block', 'events')

        if block_events:
            decoded_events = [thor_decode_event(e) for e in block_events]
            await self.pass_data_to_listeners(decoded_events)


class NativeScannerTX(NativeScanner):
    SUBSCRIBE_NEW_TX = {"jsonrpc": "2.0", "method": "subscribe", "params": ["tm.event='Tx'"], "id": 1}

    async def on_connected(self):
        self.logger.info('Connected, subscribing to new data...')
        await self.ws.send(json.dumps(self.SUBSCRIBE_NEW_TX))

    async def handle_wss_message(self, reply: dict):
        block = safe_get(reply, 'result', 'data', 'value', 'block')
        raw_txs = safe_get(block, 'data', 'txs')
        if raw_txs:
            block_height = safe_get(block, 'header', 'height')
            self.logger.info(f'Got block #{block_height} with {len(raw_txs)} transactions.')
            txs = [NativeThorTx.from_base64(item) for item in raw_txs]
            await self.pass_data_to_listeners(txs)
