import json
from urllib.parse import urlparse, urlunparse

from proto.access import thor_decode_event
from services.lib.delegates import WithDelegates
from services.lib.utils import safe_get
from services.lib.web_sockets import WSClient


# not used yet
class NativeScannerWS(WSClient, WithDelegates):
    REPLY_TIMEOUT = 20.0
    PING_TIMEOUT = 0  # will reconnect on timeout, without pinging
    SLEEP_TIME = 5.0

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


# not used yet
class NativeScannerBlockEventsWS(NativeScannerWS):
    SUBSCRIBE_NEW_BLOCK = {"jsonrpc": "2.0", "method": "subscribe", "params": ["tm.event='NewBlock'"], "id": 1}

    async def on_connected(self):
        self.logger.info('Connected, subscribing to new data...')
        await self.ws.send(json.dumps(self.SUBSCRIBE_NEW_BLOCK))

    async def handle_wss_message(self, reply: dict):
        block_events = safe_get(reply, 'result', 'data', 'value', 'result_end_block', 'events')

        if block_events:
            decoded_events = [thor_decode_event(e, 0) for e in block_events]
            await self.pass_data_to_listeners(decoded_events)


# not used yet
class NativeScannerTransactionWS(NativeScannerWS):
    SUBSCRIBE_NEW_TX = {"jsonrpc": "2.0", "method": "subscribe", "params": ["tm.event='Tx'"], "id": 1}

    async def on_connected(self):
        self.logger.info('Connected, subscribing to new data...')
        await self.ws.send(json.dumps(self.SUBSCRIBE_NEW_TX))

    async def handle_wss_message(self, reply: dict):
        tx_result = safe_get(reply, 'result', 'data', 'value', 'TxResult')
        events = safe_get(reply, 'result', 'events')

        if events:
            height = int(events['tx.height'][0])
            await self._push_tx((tx_result, events, height), height)

    async def _push_tx(self, tx, height):
        if tx:
            self._buffer.append(tx)
        if self._current_height != height:
            await self.pass_data_to_listeners(self._buffer)
            self._buffer = []
            self._current_height = height

    def __init__(self, node_rpc_url):
        super().__init__(node_rpc_url)
        self._current_height = 0
        self._buffer = []
