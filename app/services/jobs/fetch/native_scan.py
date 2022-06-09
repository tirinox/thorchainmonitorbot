import json
from urllib.parse import urlparse, urlunparse

from proto import parse_thor_tx, parse_thor_tx_from_base64
from services.lib.delegates import WithDelegates
from services.lib.web_sockets import WSClient


class NativeScanner(WSClient, WithDelegates):
    def __init__(self, node_rpc_url):
        parsed = urlparse(node_rpc_url)
        wss_scheme = 'wss' if parsed.scheme == 'https' else 'ws'

        # make WebSocketURL
        wss_url = urlunparse((
            # scheme netloc path params query fragment
            wss_scheme, parsed.netloc, 'websocket', '', '', ''
        ))

        super().__init__(wss_url, reply_timeout=20, ping_timeout=20, sleep_time=6)

    SUBSCRIBE_NEW_BLOCK = {"jsonrpc": "2.0", "method": "subscribe", "params": ["tm.event='NewBlock'"], "id": 1}
    SUBSCRIBE_NEW_TX = {"jsonrpc": "2.0", "method": "subscribe", "params": ["tm.event='Tx'"], "id": 1}

    async def handle_wss_message(self, reply: dict):
        tx_obj = reply.get('result', {}).get('data', {}).get('value', {}).get('TxResult')

        if tx_obj:
            tx = parse_thor_tx_from_base64(tx_obj['tx'])
            print(tx)

    async def on_connected(self):
        self.logger.info('Connected, subscribing to new data...')
        await self.ws.send(json.dumps(self.SUBSCRIBE_NEW_TX))
