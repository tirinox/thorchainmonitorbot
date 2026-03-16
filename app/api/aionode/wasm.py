import json
import base64
from typing import List, Optional
from urllib.parse import urlencode

from api.aionode.connector import ThorConnector


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

from typing import NamedTuple


class WasmInstantiatePermission(NamedTuple):
    permission: str = 'Everybody'
    addresses: List[str] = []

    @classmethod
    def from_json(cls, j: dict) -> 'WasmInstantiatePermission':
        j = j or {}
        return cls(
            permission=str(j.get('permission', 'Everybody')),
            addresses=list(j.get('addresses', [])),
        )


class WasmCodeInfo(NamedTuple):
    code_id: int = 0
    creator: str = ''
    data_hash: str = ''
    instantiate_permission: WasmInstantiatePermission = None

    @classmethod
    def from_json(cls, j: dict) -> 'WasmCodeInfo':
        j = j or {}
        return cls(
            code_id=int(j.get('code_id', 0)),
            creator=str(j.get('creator', '')),
            data_hash=str(j.get('data_hash', '')),
            instantiate_permission=WasmInstantiatePermission.from_json(
                j.get('instantiate_permission', {})
            ),
        )


class WasmCodeInfoList(NamedTuple):
    code_infos: List[WasmCodeInfo] = []
    next_key: Optional[str] = None
    total: Optional[str] = None

    @classmethod
    def from_json(cls, j: dict) -> 'WasmCodeInfoList':
        j = j or {}
        items = [WasmCodeInfo.from_json(c) for c in j.get('code_infos', [])]
        pagination = j.get('pagination', {}) or {}
        return cls(
            code_infos=items,
            next_key=pagination.get('next_key'),
            total=pagination.get('total'),
        )

    def __iter__(self):
        return iter(self.code_infos)

    def __len__(self):
        return len(self.code_infos)


class WasmContractCreated(NamedTuple):
    block_height: int = 0
    tx_index: int = 0

    @classmethod
    def from_json(cls, j: dict) -> 'WasmContractCreated':
        j = j or {}
        return cls(
            block_height=int(j.get('block_height', 0)),
            tx_index=int(j.get('tx_index', 0)),
        )


class WasmContractInfo(NamedTuple):
    address: str = ''
    code_id: int = 0
    creator: str = ''
    admin: str = ''
    label: str = ''
    created: Optional[WasmContractCreated] = None
    ibc_port_id: str = ''
    extension: Optional[dict] = None

    @classmethod
    def from_json(cls, j: dict) -> 'WasmContractInfo':
        j = j or {}
        info = j.get('contract_info', j)  # endpoint wraps under contract_info
        return cls(
            address=str(j.get('address', '')),
            code_id=int(info.get('code_id', 0)),
            creator=str(info.get('creator', '')),
            admin=str(info.get('admin', '')),
            label=str(info.get('label', '')),
            created=WasmContractCreated.from_json(info['created']) if info.get('created') else None,
            ibc_port_id=str(info.get('ibc_port_id', '')),
            extension=info.get('extension'),
        )


class WasmContractInfoList(NamedTuple):
    contracts: List[str] = []          # plain address strings from code/{id}/contracts
    next_key: Optional[str] = None
    total: Optional[str] = None

    @classmethod
    def from_json(cls, j: dict) -> 'WasmContractInfoList':
        j = j or {}
        pagination = j.get('pagination', {}) or {}
        return cls(
            contracts=list(j.get('contracts', [])),
            next_key=pagination.get('next_key'),
            total=pagination.get('total'),
        )

    def __iter__(self):
        return iter(self.contracts)

    def __len__(self):
        return len(self.contracts)


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

class WasmContract:
    def __init__(self, connector: ThorConnector, contract_address: str):
        self._connector = connector
        self.contract_address = contract_address

    def url(self, sub_path: str) -> str:
        return f'/cosmwasm/wasm/v1/contract/{self.contract_address}/{sub_path}'

    async def query_contract(self, query: dict) -> dict:
        """Execute a smart query against the contract. Returns raw dict."""
        query_b64 = base64.b64encode(json.dumps(query).encode()).decode()
        url = self.url(f"smart/{query_b64}")
        return await self._connector.query_raw(url)

    async def get_contract_info(self) -> WasmContractInfo:
        """Fetch the on-chain metadata for this contract."""
        raw = await self._connector.query_raw(
            f'/cosmwasm/wasm/v1/contract/{self.contract_address}'
        )
        return WasmContractInfo.from_json(raw)

    async def get_contract_history(self) -> List[dict]:
        """Fetch the instantiate/migrate history entries (raw dicts)."""
        raw = await self._connector.query_raw(
            f'/cosmwasm/wasm/v1/contract/{self.contract_address}/history'
        )
        return raw.get('entries', [])

    @property
    def connector(self) -> ThorConnector:
        return self._connector

    @connector.setter
    def connector(self, value: ThorConnector):
        self._connector = value


class WasmCodeManager:
    def __init__(self, connector: ThorConnector):
        self._connector = connector

    async def get_code_list(self, pg_limit: int = 100, pg_key: Optional[str] = None) -> WasmCodeInfoList:
        """
        Return a page of WasmCodeInfo objects.
        Pass the returned ``next_key`` as ``pg_key`` to fetch subsequent pages.
        """
        base_url = '/cosmwasm/wasm/v1/code'
        params = {}
        if pg_key is not None:
            params['pagination.key'] = pg_key
        if pg_limit is not None:
            params['pagination.limit'] = pg_limit

        query_string = urlencode(params)
        url = f"{base_url}?{query_string}" if query_string else base_url
        raw = await self._connector.query_raw(url)
        return WasmCodeInfoList.from_json(raw)

    async def get_all_codes(self, pg_limit: int = 100) -> List[WasmCodeInfo]:
        """Fetch all code infos, following pagination automatically."""
        results = []
        next_key = None
        while True:
            page = await self.get_code_list(pg_limit=pg_limit, pg_key=next_key)
            results.extend(page.code_infos)
            next_key = page.next_key
            if not next_key:
                break
        return results

    async def get_code_info(self, code_id: int) -> WasmCodeInfo:
        """Fetch metadata for a single code ID."""
        raw = await self._connector.query_raw(f'/cosmwasm/wasm/v1/code/{code_id}')
        # response wraps under 'code_info'
        info = raw.get('code_info', raw)
        info.setdefault('code_id', code_id)
        return WasmCodeInfo.from_json(info)

    async def get_contracts_of_code(
        self,
        code_id: int,
        pg_limit: int = 100,
        pg_key: Optional[str] = None,
        count_total: bool = False,
    ) -> WasmContractInfoList:
        """
        Return a page of contract addresses instantiated from ``code_id``.
        Pass the returned ``next_key`` as ``pg_key`` to fetch subsequent pages.
        Set ``count_total=True`` to ask the node to populate pagination.total
        (note: many nodes return "0" when this flag is absent).
        """
        params: dict = {'pagination.limit': pg_limit}
        if pg_key is not None:
            params['pagination.key'] = pg_key
        if count_total:
            params['pagination.count_total'] = 'true'
        qs = urlencode(params)
        url = f'/cosmwasm/wasm/v1/code/{code_id}/contracts?{qs}'
        raw = await self._connector.query_raw(url)
        return WasmContractInfoList.from_json(raw)

    async def get_all_contracts_of_code(self, code_id: int, pg_limit: int = 100) -> List[str]:
        """Fetch all contract addresses for a code ID, following pagination automatically."""
        results = []
        next_key = None
        while True:
            page = await self.get_contracts_of_code(code_id, pg_limit=pg_limit, pg_key=next_key)
            results.extend(page.contracts)
            next_key = page.next_key
            if not next_key:
                break
        return results
