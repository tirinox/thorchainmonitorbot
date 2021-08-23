from typing import List, NamedTuple

import ujson

from services.lib.web_sockets import WSClient

THORMON_WSS_ADDRESS = 'wss://thormon.nexain.com/cable'
THORMON_ORIGIN = 'https://thorchain.network'
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ' \
             'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36'


class ThorMonChainHeight(NamedTuple):
    chain: str
    height: int

    @classmethod
    def from_json(cls, j):
        return cls(chain=j.get('chain', ''), height=int(j.get('height', 0)))


class ThorMonNode(NamedTuple):
    node_address: str
    ip_address: str
    bond: int
    current_award: int
    slash_points: int
    version: str
    status: str
    observe_chains: List[ThorMonChainHeight]
    requested_to_leave: bool
    forced_to_leave: bool
    leave_height: int
    status_since: int
    thor: bool
    rpc: bool
    midgard: bool
    bifrost: bool

    @classmethod
    def from_json(cls, j):
        raw_chains = j.get('observe_chains') or []
        chains = [ThorMonChainHeight.from_json(o) for o in raw_chains]
        return cls(
            node_address=j.get('node_address', ''),
            ip_address=j.get('ip_address', ''),
            bond=int(j.get('bond', 0)),
            current_award=int(j.get('current_award', 0)),
            slash_points=int(j.get('slash_points', 0)),
            version=j.get('version', '0.0.0'),
            status=j.get('status', 'Standby'),
            observe_chains=chains,
            requested_to_leave=bool(j.get('requested_to_leave')),
            forced_to_leave=bool(j.get('forced_to_leave')),
            leave_height=int(j.get('leave_height', 0)),
            status_since=int(j.get('status_since', 0)),
            thor=bool(j.get('thor')),
            rpc=bool(j.get('rpc')),
            midgard=bool(j.get('midgard')),
            bifrost=bool(j.get('bifrost')),
        )


class ThorMonAnswer(NamedTuple):
    last_block: int
    next_churn: int
    nodes: List[ThorMonNode]

    @classmethod
    def from_json(cls, j):
        return cls(
            last_block=int(j.get('last_block', 0)),
            next_churn=int(j.get('next_churn', 0)),
            nodes=[ThorMonNode.from_json(node) for node in j.get('nodes', [])]
        )


class ThormonWSSClient(WSClient):
    def __init__(self, net="mainnet", reply_timeout=10, ping_timeout=5, sleep_time=5):
        self.net = net
        headers = {
            'Origin': THORMON_ORIGIN,
            'Sec-WebSocket-Extensions': 'permessage-deflate; client_max_window_bits',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'User-Agent': ''
        }

        super().__init__(THORMON_WSS_ADDRESS, reply_timeout, ping_timeout, sleep_time, headers=headers)

    async def handle_message(self, j):
        message = j.get('message', {})
        if isinstance(message, dict):
            answer = ThorMonAnswer.from_json(message)
            print(f'Incoming: {answer}')  # todo
        else:
            print(f'Text msg: {j}')

    async def on_connected(self):
        self.logger.info('Connected to THORMon. Subscribing to the ThorchainChannel channel...')
        ident_encoded = ujson.dumps({"channel": "ThorchainChannel", "network": self.net})
        await self.send_message({
            "command": "subscribe", "identifier": ident_encoded
        })
