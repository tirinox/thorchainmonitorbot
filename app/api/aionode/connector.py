import asyncio
import logging
from typing import Dict

from aiohttp import ClientSession, ClientError, ServerDisconnectedError

from .env import ThorEnvironment
from .nodeclient import ThorNodeClient
from .types import *


class ThorConnector:
    # --- METHODS ----

    async def query_custom_path(self, path):
        data = await self._request(path)
        return data

    async def query_raw(self, path, is_rpc=False):
        return await self._request(path, is_rpc=is_rpc)

    async def query_node_accounts(self) -> List[ThorNodeAccount]:
        data = await self._request(self.env.path_nodes)
        return [ThorNodeAccount.from_json(j) for j in data] if data else []

    async def query_queue(self) -> ThorQueue:
        data = await self._request(self.env.path_queue)
        return ThorQueue.from_json(data)

    async def query_pools(self, height=None) -> List[ThorPool]:
        if height:
            path = self.env.path_pools_height
        else:
            path = self.env.path_pools
        data = await self._request(path, treat_empty_as_ok=False, height=height)
        return [ThorPool.from_json(j) for j in data] if data else None

    async def query_pool(self, pool: str, height=None) -> ThorPool:
        if height:
            path = self.env.path_pool_height.format(pool=pool)
        else:
            path = self.env.path_pool.format(pool=pool)
        data = await self._request(path, height=height)
        return ThorPool.from_json(data)

    async def query_last_blocks(self) -> List[ThorLastBlock]:
        data = await self._request(self.env.path_last_blocks)
        return [ThorLastBlock.from_json(j) for j in data] if isinstance(data, list) else [ThorLastBlock.from_json(data)]

    async def query_constants(self) -> ThorConstants:
        data = await self._request(self.env.path_constants)
        return ThorConstants.from_json(data) if data else ThorConstants()

    async def query_mimir(self, height=None) -> ThorMimir:
        data = await self._request(self.env.path_mimir, height=height)

        return ThorMimir.from_json(data) if data else ThorMimir()

    async def query_mimir_votes(self) -> List[ThorMimirVote]:
        response = await self._request(self.env.path_mimir_votes)
        mimirs = response.get('mimirs', [])
        return ThorMimirVote.from_json_array(mimirs)

    async def query_mimir_node_accepted(self) -> dict:
        response = await self._request(self.env.path_mimir_nodes)
        return response or {}

    async def query_chain_info(self) -> Dict[str, ThorChainInfo]:
        data = await self._request(self.env.path_inbound_addresses)
        if isinstance(data, list):
            info_list = [ThorChainInfo.from_json(j) for j in data]
        else:
            # noinspection PyUnresolvedReferences
            current = data.get('current', {})  # single-chain
            info_list = [ThorChainInfo.from_json(j) for j in current]
        return {info.chain: info for info in info_list}

    async def query_vault(self, vault_type=ThorVault.TYPE_ASGARD, height=None) -> List[ThorVault]:
        path = self.env.path_vault_asgard if vault_type == ThorVault.TYPE_ASGARD else self.env.path_vault_yggdrasil
        data = await self._request(path, height=height)
        return [ThorVault.from_json(v) for v in data]

    async def query_balance(self, address: str) -> ThorBalances:
        path = self.env.path_balance.format(address=address)
        data = await self._request(path)
        return ThorBalances.from_json(data, address)

    async def query_tendermint_block_raw(self, height):
        path = self.env.path_block_by_height
        data = await self._request(path, is_rpc=True, height=height)
        return data

    async def query_thorchain_block_raw(self, height):
        path = self.env.path_thorchain_block_by_height
        data = await self._request(path, height=height)
        return data

    async def query_genesis(self):
        data = await self._request(self.env.path_genesis, is_rpc=True)
        return data['result']['genesis'] if data else None

    async def query_native_status_raw(self):
        return await self._request(self.env.path_status, is_rpc=True)

    async def query_native_block_results_raw(self, height=None):
        url = self.env.path_block_results
        return await self._request(url, is_rpc=True, height=height)

    async def query_liquidity_providers(self, asset, height=None):
        url = self.env.path_liq_providers.format(asset=asset)
        data = await self._request(url, height=height)
        if data:
            return [ThorLiquidityProvider.from_json(p) for p in data]

    async def query_liquidity_provider(self, asset, address, height=None):
        url = self.env.path_liq_provider_details.format(asset=asset, address=address)
        data = await self._request(url, height=height)
        if data:
            return ThorLiquidityProvider.from_json(data)

    async def query_network(self, height=None):
        url = self.env.path_network
        data = await self._request(url, height=height)
        if data:
            return ThorNetwork.from_json(data)

    async def query_swapper_clout(self, address: str, height=None):
        url = self.env.path_swapper_clout.format(address=address)
        data = await self._request(url, height=height)
        if data:
            return ThorSwapperClout.from_json(data)

    async def query_tx_status(self, tx_hash: str):
        url = self.env.path_tx_status.format(txid=tx_hash)
        data = await self._request(url)
        if data:
            return ThorTxStatus.from_json(data)

    async def query_tx_stages(self, tx_hash: str):
        url = self.env.path_tx_stages.format(txid=tx_hash)
        data = await self._request(url)
        return data

    async def query_tx_details(self, tx_hash: str):
        url = self.env.path_tx_details.format(txid=tx_hash)
        data = await self._request(url)
        return data

    async def query_tx_simple(self, tx_hash: str):
        url = self.env.path_tx_simple.format(txid=tx_hash)
        data = await self._request(url)
        return data

    async def query_trade_units(self, height=None):
        url = self.env.path_trade_units
        data = await self._request(url, height=height)
        if data:
            return [ThorTradeUnits.from_json(p) for p in data]

    async def query_trade_accounts(self, asset, height=None):
        url = self.env.path_trade_accounts.format(asset=asset)
        data = await self._request(url, height=height)
        if data:
            return [ThorTradeAccount.from_json(p) for p in data]

    async def query_trade_account(self, address, height=None) -> List[ThorTradeAccount]:
        url = self.env.path_trade_account.format(wallet=address)
        data = await self._request(url, treat_empty_as_ok=True, height=height)
        if data:
            if isinstance(data, list):
                return [ThorTradeAccount.from_json(p) for p in data]
            else:
                return [ThorTradeAccount.from_json(data)]

        return []

    async def query_runepool(self, height=None):
        url = self.env.path_runepool
        data = await self._request(url, height=height)
        if data:
            return ThorRunePool.from_json(data)

    async def query_runepool_providers(self, height=None):
        url = self.env.path_runepool_providers
        data = await self._request(url, height=height)
        if data:
            return [ThorRunePoolProvider.from_json(p) for p in data]

    async def query_swap_quote(self, from_asset, to_asset, amount, destination='', refund_address=None,
                               streaming_interval=0, streaming_quantity=0, tolerance_bps=0, affiliate_bps=0,
                               affiliate=0,
                               height=None):

        query = {}

        if from_asset:
            query['from_asset'] = from_asset

        if to_asset:
            query['to_asset'] = to_asset

        if amount:
            query['amount'] = amount

        if destination:
            query['destination'] = destination

        if refund_address:
            query['refund_address'] = refund_address

        if streaming_interval:
            query['streaming_interval'] = streaming_interval

        if streaming_quantity:
            query['streaming_quantity'] = streaming_quantity

        if tolerance_bps:
            query['tolerance_bps'] = tolerance_bps

        if affiliate_bps:
            query['affiliate_bps'] = affiliate_bps

        if affiliate:
            query['affiliate'] = affiliate

        if height:
            query['height'] = height

        url = self.env.path_quote_swap + '?' + '&'.join([f'{k}={v}' for k, v in query.items()])

        data = await self._request(url)
        if data:
            return data

    async def query_secured_assets(self, height=None):
        url = self.env.path_secured_assets
        data = await self._request(url, treat_empty_as_ok=True, height=height)
        if data:
            return [ThorSecuredAsset.from_json(p) for p in data] if isinstance(data, list) else [
                ThorSecuredAsset.from_json(data)]

    async def query_holders(self, asset: str, height=None):
        asset = asset.lower()
        url = self.env.path_holders.format(asset=asset)
        data = await self._request(url, paginated=True, height=height, collect_key='denom_owners')
        return data

    # ---- Internal ----

    def __init__(self, env: ThorEnvironment, session: ClientSession, logger=None, extra_headers=None,
                 additional_envs=None, silent=True):
        self.session = session
        self.env = env
        self.silent = silent
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._clients = [
            self._make_client(env, extra_headers)
        ]

        if additional_envs:
            if not isinstance(additional_envs, (list, tuple)):
                additional_envs = [additional_envs]

            for env in additional_envs:
                self._clients.append(self._make_client(env, extra_headers))

    def _make_client(self, env: ThorEnvironment, extra_headers):
        return ThorNodeClient(self.session, logger=self.logger, env=env,
                              extra_headers=extra_headers)

    def set_client_id_for_all(self, client_id):
        for client in self._clients:
            client.set_client_id_header(client_id)

    async def _request(self, path, is_rpc=False, treat_empty_as_ok=True, paginated=False, height=None, collect_key=''):
        for client in self._clients:
            for attempt in range(1, client.env.retries + 1):
                if attempt > 1:
                    self.logger.debug(f'Retry #{attempt} for path "{path}"')
                try:
                    if paginated:
                        data = await client.paginated_request(path, height=height, result_key=collect_key)
                    else:
                        data = await client.request(path, is_rpc=is_rpc, height=height)

                    if treat_empty_as_ok:
                        return data
                    else:
                        if data:
                            # only non-empty data is considered as valid
                            if isinstance(data, dict) and data.get('code', 0) != 0:
                                self.logger.error(f'Error in THORNode: {data}')
                                raise ConnectionError(f'Error in THORNode: {data}')

                            return data
                        else:
                            # if data is empty and treat_empty_as_ok==False, try next client
                            break  # breaks the retry loop
                except NotImplementedError:
                    # Do no retries, no backups. Something is wrong with your code
                    raise
                except (FileNotFoundError, AttributeError,
                        ConnectionError, asyncio.TimeoutError,
                        ClientError, ServerDisconnectedError) as e:
                    if not self.silent:
                        raise
                    else:
                        err_type = type(e).__name__
                        self.logger.warning(
                            f'#{attempt}. Failed to query {client} for "{client.connection_url(path, is_rpc)}" (err: {err_type}).')
                if d := client.env.retry_delay:
                    self.logger.debug(f'#{attempt}. Delay before retry: {d} sec...')
                    await asyncio.sleep(d)
