import asyncio
import json
import struct
from typing import Optional, List, Iterable, Dict

from proto.thor_types import THORName, THORNameAlias
from services.lib.config import Config
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.db import DB
from services.lib.midgard.connector import MidgardConnector
from services.lib.utils import WithLogger


# THORName: address[owner] -> many of [name] -> many of [address (thor + chains)]
# Here we basically don't care about owners of THORNames.
# We must have API for Address -> THORName, and THORName -> [Address] resolution
class NameService(WithLogger):
    def __init__(self, db: DB, cfg: Config, midgard: MidgardConnector):
        super().__init__()
        self.db = db
        self.cfg = cfg
        self.midgard = midgard
        self._known_address = {}
        self._known_names = {}
        self._load_preconfigured_names()

        self._thorname_enabled = cfg.as_str('names.thorname.enabled', True)
        self._thorname_expire = int(parse_timespan_to_seconds(cfg.as_str('names.thorname.expire', '24h'))) or None

        if self._thorname_enabled:
            self.logger.info(f'THORName is enabled with expire time of {self._thorname_expire} sec.')

    async def safely_load_thornames_from_address_set(self, addresses: Iterable):
        if not addresses:
            return
        try:
            return await self.lookup_multiple_names_by_addresses(addresses)
        except Exception:
            self.logger.exception(f'Something went wrong. That is OK', exc_info=True)

    def lookup_name_by_address_local(self, address: str) -> Optional[THORName]:
        return self._known_address.get(address)

    async def lookup_name_by_address(self, address: str) -> Optional[THORName]:
        if not address:
            return

        local_results = self.lookup_name_by_address_local(address)
        if local_results:
            return local_results

        if not self._thorname_enabled:
            return

        names = await self._load_name_list(address)
        if names is None:
            names = await self.thorname_reversed_lookup(address)
            await self._save_name_list(address, names)
            if not names:
                return

        name = names[0]
        if len(names) > 1:
            self.logger.warning(f'Address {address} resolves to more than 1 THORNames: "{names}". I will take "{name}"')

        thorname = await self._load_thor_name(name)
        if not thorname:
            thorname = await self.thorname_lookup(name)
            if thorname:
                await self._save_thor_name(thorname)
            else:
                self.logger.warning(f'THORName "{name}" failed to be loaded!')
                return
        return thorname

    async def lookup_multiple_names_by_addresses(self, addresses: Iterable) -> Dict[str, THORName]:
        thor_names = await asyncio.gather(
            *[self.lookup_name_by_address(address) for address in addresses]
        )
        entries = [(address, thor_name) for address, thor_name in zip(addresses, thor_names)]
        return dict(entries)

    async def lookup_address_by_name(self, name: str) -> Optional[str]:
        name = name.strip()
        if name in self._known_names:
            return self._known_names[name]

    # name -> [address]
    async def thorname_lookup(self, name: str) -> Optional[THORName]:
        """
        Returns an array of chains and their addresses associated with the given THORName
        """
        results = await self.midgard.request_random_midgard(f'/v2/thorname/lookup/{name}')
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
    async def thorname_reversed_lookup(self, address: str) -> List[str]:
        """
        Returns an array of THORNames associated with the given address
        """
        results = await self.midgard.request_random_midgard(f'/v2/thorname/rlookup/{address}')
        return results or []

    async def get_thornames_owned_by_address(self, thor_address: str):
        """
        Returns an array of THORNames owned by the address.
        The address is not necessarily an associated address for those thornames.
        """
        results = await self.midgard.request_random_midgard(f'/v2/thorname/owner/{thor_address}')
        return results or []

    def _load_preconfigured_names(self):
        name_dic: dict = self.cfg.get_pure('names.preconfig', {})
        for address, label in name_dic.items():
            if address and label:
                self._known_address[address] = THORName(
                    label, 0, address.encode()
                )
                self._known_names[label] = address

    @staticmethod
    def _key_thorname_to_addresses(name: str):
        return f'THORName:Entries:{name}'

    @staticmethod
    def _key_address_to_names(address: str):
        return f'THORName:Address-to-Names:{address}'

    async def _save_name_list(self, address: str, names: List[str]):
        await self.db.redis.set(self._key_address_to_names(address),
                                value=json.dumps(names),
                                ex=self._thorname_expire)

    async def _load_name_list(self, address: str) -> List[str]:
        data = await self.db.redis.get(self._key_address_to_names(address))
        return json.loads(data) if data else None

    async def _save_thor_name(self, thorname: THORName):
        if not thorname:
            return
        await self.db.redis.set(
            self._key_thorname_to_addresses(thorname.name),
            value=thorname.to_json(),
            ex=self._thorname_expire
        )

    async def _load_thor_name(self, name: str) -> Optional[THORName]:
        if not name:
            return

        data = await self.db.redis.get(self._key_thorname_to_addresses(name))
        if not data:
            return

        try:
            return THORName().from_json(data)
        except (TypeError, struct.error):
            return

    async def clear_cache_for_name(self, name: str):
        await self.db.redis.delete(self._key_thorname_to_addresses(name))

    async def clear_cache_for_address(self, address: str):
        await self.db.redis.delete(self._key_address_to_names(address))
