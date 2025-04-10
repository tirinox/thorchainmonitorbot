import json
from urllib.parse import urlencode

from api.aionode.connector import ThorConnector
import base64


class WasmContract:
    def __init__(self, connector: ThorConnector, contract_address: str):
        self._connector = connector
        self.contract_address = contract_address

    def url(self, sub_path: str) -> str:
        return f'/cosmwasm/wasm/v1/contract/{self.contract_address}/{sub_path}'

    async def query_contract(self, query: dict) -> dict:
        # base64 encode
        query_b64 = base64.b64encode(json.dumps(query).encode()).decode()
        url = self.url(f"smart/{query_b64}")
        result = await self._connector.query_raw(url)
        return result


class WasmCodeManager:
    def __init__(self, connector: ThorConnector):
        self._connector = connector

    async def get_code_list(self, pg_limit=100, pg_key=None):
        base_url = '/cosmwasm/wasm/v1/code'
        params = {}

        if pg_key is not None:
            params['pagination.key'] = pg_key
        if pg_limit is not None:
            params['pagination.limit'] = pg_limit

        query_string = urlencode(params)
        url = f"{base_url}?{query_string}" if query_string else base_url

        return await self._connector.query_raw(url)

    async def get_contract_of_code_id(self, code_id):
        return await self._connector.query_raw(f'/cosmwasm/wasm/v1/code/{code_id}/contracts')
