import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

from aiohttp import ClientSession

from jobs.fetch.cached.base import CachedDataSource
from lib.date_utils import HOUR
from lib.db import DB
from lib.path import get_data_path, get_app_path


class RujiraContractNameCache(CachedDataSource[Dict[str, str]]):
    """
    Read-through cache for friendly CosmWasm contract names.
    Lookup/update strategy:
      1. Periodically try to download the canonical JSON from GitHub.
      2. If the remote is unavailable, fall back to the bundled local JSON file.
      3. If both are unavailable, restore the last good mapping from Redis.
    """
    REDIS_KEY = 'RujiraContractNameCache:names'
    DEFAULT_SOURCE_URL = (
        'https://raw.githubusercontent.com/thorchain/'
        'thorchain-explorer-v2/main/data/contracts/rujira-mainnet.json'
    )
    DEFAULT_LOCAL_FILE = Path(get_data_path()) / 'rujira' / 'rujira-mainnet.json'
    def __init__(
        self,
        session: Optional[ClientSession] = None,
        db: Optional[DB] = None,
        source_url: str = DEFAULT_SOURCE_URL,
        local_file: Union[str, Path] = DEFAULT_LOCAL_FILE,
        cache_period: float = 6 * HOUR,
    ):
        super().__init__(cache_period=cache_period, retry_times=2, retry_delay=1.0)
        self.session = session
        self.db = db
        self.source_url = source_url
        self.local_file = self._resolve_local_file(local_file)
    @staticmethod
    def _resolve_local_file(local_file: Union[str, Path]) -> Path:
        path = Path(local_file)
        if path.is_absolute():
            return path
        return Path(get_app_path()) / path
    @staticmethod
    def _clean(value: Any) -> str:
        return value.strip() if isinstance(value, str) else ''
    @classmethod
    def _humanize_slug(cls, value: Any) -> str:
        value = cls._clean(value)
        if not value:
            return ''
        return re.sub(r'\s+', ' ', value.replace('-', ' ').replace('_', ' ')).strip()
    @classmethod
    def _pick_friendly_name(cls, address_info: dict, family_info: dict) -> str:
        for candidate in (
            address_info.get('name'),
            family_info.get('name'),
            address_info.get('product'),
            family_info.get('product'),
            address_info.get('contractLabel'),
        ):
            if cleaned := cls._clean(candidate):
                return cleaned
        for candidate in (
            address_info.get('contractName'),
            address_info.get('family'),
        ):
            if humanized := cls._humanize_slug(candidate):
                return humanized
        return ''
    @classmethod
    def extract_names_from_payload(cls, payload: dict) -> Dict[str, str]:
        families = payload.get('families') or {}
        addresses = payload.get('addresses') or {}
        if not isinstance(families, dict) or not isinstance(addresses, dict):
            raise ValueError('Unexpected Rujira contracts JSON structure.')
        result: Dict[str, str] = {}
        for address, address_info in addresses.items():
            if not isinstance(address_info, dict):
                continue
            family_key = cls._clean(address_info.get('family'))
            family_info = families.get(family_key) if family_key else {}
            if not isinstance(family_info, dict):
                family_info = {}
            friendly_name = cls._pick_friendly_name(address_info, family_info)
            if friendly_name:
                result[str(address)] = friendly_name
        if not result:
            raise ValueError('No contract names found in Rujira contracts JSON.')
        return result
    async def _save_to_redis(self, mapping: Dict[str, str]) -> None:
        if self.db is None or not mapping:
            return
        try:
            r = await self.db.get_redis()
            await r.set(self.REDIS_KEY, json.dumps(mapping))
            self.logger.info(
                f"RujiraContractNameCache: saved {len(mapping)} name(s) to Redis key '{self.REDIS_KEY}'."
            )
        except Exception as exc:
            self.logger.warning(f'RujiraContractNameCache: failed to save to Redis: {exc}')
    async def _load_from_redis(self) -> Optional[Dict[str, str]]:
        if self.db is None:
            return None
        try:
            r = await self.db.get_redis()
            raw = await r.get(self.REDIS_KEY)
            if not raw:
                return None
            mapping = json.loads(raw)
            if not isinstance(mapping, dict) or not mapping:
                raise ValueError('Redis payload is empty or malformed.')
            result = {
                str(address): self._clean(name)
                for address, name in mapping.items()
                if self._clean(name)
            }
            if not result:
                raise ValueError('Redis payload did not contain any usable names.')
            self.logger.info(
                f"RujiraContractNameCache: restored {len(result)} name(s) from Redis key '{self.REDIS_KEY}'."
            )
            return result
        except Exception as exc:
            self.logger.warning(f'RujiraContractNameCache: failed to load from Redis: {exc}')
            return None
    async def _load_remote(self) -> Dict[str, str]:
        if self.session is None:
            raise RuntimeError('HTTP session is not available.')
        async with self.session.get(self.source_url) as response:
            if response.status != 200:
                raise RuntimeError(f'HTTP {response.status} for {self.source_url}')
            payload = json.loads(await response.text())
        mapping = self.extract_names_from_payload(payload)
        self.logger.info(
            f'RujiraContractNameCache: loaded {len(mapping)} name(s) from GitHub source.'
        )
        return mapping
    async def _load_local(self) -> Dict[str, str]:
        with self.local_file.open('r', encoding='utf-8') as f:
            payload = json.load(f)
        mapping = self.extract_names_from_payload(payload)
        self.logger.info(
            f'RujiraContractNameCache: loaded {len(mapping)} name(s) from local file {self.local_file}.'
        )
        return mapping
    async def _load(self) -> Dict[str, str]:
        try:
            mapping = await self._load_remote()
            await self._save_to_redis(mapping)
            return mapping
        except Exception as exc:
            self.logger.warning(f'RujiraContractNameCache: remote refresh failed: {exc}')
        try:
            mapping = await self._load_local()
            await self._save_to_redis(mapping)
            return mapping
        except Exception as exc:
            self.logger.warning(f'RujiraContractNameCache: local fallback failed: {exc}')
        if cached := await self._load_from_redis():
            return cached
        raise RuntimeError('RujiraContractNameCache: no data available from GitHub, local file, or Redis.')
    async def get_name(self, address: str) -> str:
        mapping = await self.get()
        return mapping.get(address, '')
    async def resolve_name(self, address: str, fallback: str = '') -> str:
        return await self.get_name(address) or fallback or ''
