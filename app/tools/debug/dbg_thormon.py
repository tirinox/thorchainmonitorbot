import asyncio
import json
import logging

import ujson
import websockets

from services.lib.web_sockets import WSClient


class ThormonWSSClient(WSClient):
    def __init__(self, reply_timeout=10, ping_timeout=5, sleep_time=5):
        headers = {
            'Origin': 'https://thorchain.network',
            'Sec-WebSocket-Extensions': 'permessage-deflate; client_max_window_bits',
            # 'Sec-WebSocket-Key': 'XqP3Zc5nS0yaysvhamDrcQ==',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36'
        }

        super().__init__('wss://thormon.nexain.com/cable/', reply_timeout, ping_timeout, sleep_time, headers=headers)

    async def handle_message(self, j):
        print(f'Incoming: {j}')

    async def on_connected(self):
        print('Connected!!')
        ident_encoded = ujson.dumps({"channel": "ThorchainChannel", "network": "mainnet"})
        await self.send_message({
            "command": "subscribe", "identifier": ident_encoded
        })


async def main():
    logging.basicConfig(level=logging.DEBUG)
    client = ThormonWSSClient()
    await client.listen_forever()


if __name__ == '__main__':
    asyncio.run(main())
