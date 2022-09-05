import asyncio
from typing import Optional, List, Iterable, Dict

from proto.thor_types import THORName, THORNameAlias
from services.lib.config import Config
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.db import DB
from services.lib.midgard.connector import MidgardConnector


# THORName: address[owner] -> many of [name] -> many of [address (thor + chains)]

class NameService:
    def __init__(self, db: DB, cfg: Config, midgard: MidgardConnector):
        self.db = db
        self.cfg = cfg
        self.midgard = midgard
        self._known_address = {}
        self._known_names = {}
        self._load_preconfigured_names()

        self._thorname_enabled = cfg.as_str('name.thorname.enabled', True)
        self._thorname_expire = parse_timespan_to_seconds(cfg.as_str('name.thorname.expire', '24h'))

    def _key_thorname(self, name: str):
        return f'THORName:{name}'

    def lookup_name_by_address_local(self, address: str) -> Optional[THORName]:
        return self._known_address.get(address)

    async def lookup_name_by_address(self, address: str) -> Optional[THORName]:
        local_results = self.lookup_name_by_address_local(address)
        if local_results:
            return local_results

        # if self._thorname_enabled:
        #     key = self._key_thorname(address)
        #     name = await self.db.redis.get(key)
        # todo lookup!
        # 1) read thornames from Database
        # 2) if any and not expired => return it
        # 3) if not or expired:
        # 4) use thor_name_reversed_lookup => [names]
        # 5) thor_name_lookup(names[0]) if names else None

    async def lookup_multiple_names_by_addresses(self, addresses: Iterable) -> Dict[str, THORName]:
        thor_names = await asyncio.gather(
            *[(address, self.lookup_name_by_address(address)) for address in addresses]
        )
        return dict(thor_names)

    async def lookup_address_by_name(self, name: str) -> Optional[str]:
        name = name.strip()
        if name in self._known_names:
            return self._known_names[name]

    # name -> [address]
    async def thor_name_lookup(self, name: str) -> Optional[THORName]:
        results = await self.midgard.request_random_midgard(f'/thorname/lookup/{name}')
        if results:
            return THORName(
                name=name,
                expire_block_height=int(results['expire']),
                owner=results['owner'].encode(),
                aliases=[
                    THORNameAlias(alias['chain'], alias['address']) for alias in results['entries']
                ]
            )

    # address -> [name as str]
    async def thor_name_reversed_lookup(self, address: str) -> List[str]:
        results = await self.midgard.request_random_midgard(f'/thorname/rlookup/{address}')
        return results or []

    async def thor_name_owns(self, thor_address: str):
        results = await self.midgard.request_random_midgard(f'/thorname/owner/{thor_address}')
        return results or []

    def _load_preconfigured_names(self):
        name_dic: dict = self.cfg.get_pure('names.preconfig', {})
        for address, label in name_dic.items():
            if address and label:
                self._known_address[address] = THORName(
                    label, 0, address.encode()
                )
                self._known_names[label] = address
