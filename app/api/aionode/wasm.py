import json

from api.aionode.connector import ThorConnector
import base64


class WasmContract:
    def __init__(self, connector: ThorConnector, contract: str):
        self._connector = connector
        self.contract = contract

    def url(self, sub_path: str) -> str:
        return f'/cosmwasm/wasm/v1/contract/{self.contract}/{sub_path}'

    async def query_contract(self, query: dict) -> dict:
        # base64 encode
        query_b64 = base64.b64encode(json.dumps(query).encode()).decode()
        url = self.url(f"smart/{query_b64}")
        result = await self._connector.query_raw(url)
        return result
