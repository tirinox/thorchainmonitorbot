import json
import os.path
from datetime import datetime
from typing import NamedTuple, Optional

import ujson

from services.jobs.fetch.base import BaseFetcher, WithDelegates
from services.lib.constants import NetworkIdents
from services.lib.date_utils import date_parse_rfc_z_no_ms, now_ts
from services.lib.depcont import DepContainer
from services.lib.web_sockets import WSClient
from services.models.thormon import ThorMonAnswer

THORMON_WSS_ADDRESS = 'wss://thormon.nexain.com/cable'
THORMON_ORIGIN = 'https://thorchain.network'
THORMON_SOLVENCY_URL = 'https://thorchain-mainnet-solvency.nexain.com/api/v1/solvency/data/latest_snapshot'

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ' \
             'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36'

# fixme
DEBUG = False


class ThorMonWSSClient(WSClient, WithDelegates):
    def __init__(self, network, reply_timeout=10, ping_timeout=5, sleep_time=5):
        self._thormon_net = 'mainnet' if NetworkIdents.is_live(network) else 'testnet'
        headers = {
            'Origin': THORMON_ORIGIN,
            'Sec-WebSocket-Extensions': 'permessage-deflate; client_max_window_bits',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'User-Agent': ''
        }
        self.last_message_ts = 0.0

        super().__init__(THORMON_WSS_ADDRESS, reply_timeout, ping_timeout, sleep_time, headers=headers)

    @property
    def last_signal_sec_ago(self):
        return now_ts() - self.last_message_ts

    async def handle_wss_message(self, j):
        message = j.get('message', {})
        self.last_message_ts = now_ts()

        if isinstance(message, dict):
            if DEBUG:
                message = self._dbg_read_from_file(data=message)

            answer = ThorMonAnswer.from_json(message)
            if answer.nodes:
                self.logger.debug(f'Got WSS message. {len(answer.nodes)}, {answer.last_block = }')
                await self.handle_data(answer)
        else:
            self.logger.debug(f'Other message: {message}')

    async def on_connected(self):
        self.logger.info('Connected to THORMon. Subscribing to the ThorchainChannel channel...')
        ident_encoded = ujson.dumps({"channel": "ThorchainChannel", "network": self._thormon_net})
        await self.send_message({
            "command": "subscribe", "identifier": ident_encoded
        })

    DBG_FILE = '../temp/thormon.json'

    def _dbg_save_to_file(self, message, file=None):
        if not message:
            return
        file = file or self.DBG_FILE
        if not os.path.exists(file):
            with open(file, 'w') as f:
                json.dump(message, f)
        else:
            self.logger.warn(f'Temp "{file}" already exists.')

    def _dbg_read_from_file(self, file=None, data=None):
        try:
            file = file or self.DBG_FILE
            self.logger.warn(f'DEBUGGING: Reading file "{file}"')
            with open(file, 'r') as f:
                result = json.load(f)
                nodes = len(result.get('nodes', []))
                self.logger.warn(f'DEBUGGING: nodes = {nodes}')
                return result or data
        except Exception:
            return data


class ThorMonSolvencyAsset(NamedTuple):
    symbol: str
    is_ok: bool
    created_at: datetime
    snapshot_date: datetime
    pending_inbound_asset: float
    pool_balance: float
    vault_balance: float
    wallet_balance: float
    pool_vs_vault_diff: float
    wallet_vs_vault_diff: float
    error: Optional[str]

    @classmethod
    def from_json(cls, j):
        datum = j.get('assetDatum', {})

        return cls(
            error=j.get('error'),
            symbol=j.get('symbol', ''),
            is_ok=bool(j.get('statusOK', False)),
            created_at=date_parse_rfc_z_no_ms(datum.get('createdAt')),
            snapshot_date=date_parse_rfc_z_no_ms(datum.get('snapshotDate')),
            pending_inbound_asset=float(datum.get('pendingInboundAsset', 0.0)),
            pool_balance=float(datum.get('poolBalance', 0.0)),
            vault_balance=float(datum.get('vaultBalance', 0.0)),
            wallet_balance=float(datum.get('walletBalance', 0.0)),
            pool_vs_vault_diff=float(datum.get('poolVsVaultDiff', 0.0)),
            wallet_vs_vault_diff=float(datum.get('walletVsVaultDiff', 0.0)),
        )


class ThorMonSolvencyFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer, sleep_period=60, url=THORMON_SOLVENCY_URL):
        super().__init__(deps, sleep_period)
        self.url = url

    async def fetch(self):
        self.logger.info(f"Get solvency: {self.url}")
        async with self.deps.session.get(self.url) as resp:
            raw_data = await resp.json()
            return [ThorMonSolvencyAsset.from_json(item) for item in raw_data]
