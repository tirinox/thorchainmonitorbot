import asyncio
import json
import struct
from typing import Optional, List, Iterable, Dict, NamedTuple

from proto.types import ThorName, ThorNameAlias
from services.lib.config import Config
from services.lib.constants import Chains
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.db import DB
from services.lib.midgard.connector import MidgardConnector
from services.lib.utils import WithLogger, keys_to_lower


class NameMap(NamedTuple):
    by_name: Dict[str, ThorName]
    by_address: Dict[str, ThorName]


# ThorName: address[owner] -> many of [name] -> many of [address (thor + chains)]
# Here we basically don't care about owners of ThorNames.
# We must have API for Address -> ThorName, and ThorName -> [Address] resolution
class NameService(WithLogger):
    def __init__(self, db: DB, cfg: Config, midgard: MidgardConnector):
        super().__init__()
        self.db = db
        self.cfg = cfg
        self.midgard = midgard
        self._known_address = {}
        self._known_names = {}
        self._affiliates = {}
        self._load_preconfigured_names()

        self._thorname_enabled = cfg.as_str('names.thorname.enabled', True)
        self._thorname_expire = int(parse_timespan_to_seconds(cfg.as_str('names.thorname.expire', '24h'))) or None

        if self._thorname_enabled:
            self.logger.info(f'ThorName is enabled with expire time of {self._thorname_expire} sec.')

    async def safely_load_thornames_from_address_set(self, addresses: Iterable) -> NameMap:
        try:
            addresses = list(set(addresses))  # make it unique and strictly ordered

            thorname_by_name = await self.lookup_multiple_names_by_addresses(addresses)

            thorname_by_address = {}
            for address in addresses:
                for thorname in thorname_by_name.values():
                    if thorname and thorname != self.NO_VALUE:
                        for alias in thorname.aliases:
                            if alias.address == address:
                                thorname_by_address[address] = thorname
                                break

            return NameMap(thorname_by_name, thorname_by_address)
        except Exception:
            self.logger.exception(f'Something went wrong. That is OK', exc_info=True)
            return NameMap({}, {})

    async def lookup_name_by_address(self, address: str) -> Optional[ThorName]:
        if not address:
            return

        local_results = self.lookup_name_by_address_local(address)
        if local_results:
            return local_results

        if not self._thorname_enabled:
            return

        names = await self._cache_load_name_list(address)
        if names is None:
            names = await self.call_api_thorname_reversed_lookup(address)
            await self._cache_save_name_list(address, names)

        if not names:
            return

        # todo: find a ThorName locally or pick any of this list
        name = names[0]
        if len(names) > 1:
            self.logger.warning(f'Address {address} resolves to more than 1 ThorNames: "{names}". '
                                f'I will take the first one "{name}"')

        return await self.lookup_thorname_by_name(name)

    async def lookup_multiple_names_by_addresses(self, addresses: Iterable) -> Dict[str, ThorName]:
        if not addresses:
            return {}

        thor_names = await asyncio.gather(
            *[self.lookup_name_by_address(address) for address in addresses]
        )
        entries = [(address, thor_name) for address, thor_name in zip(addresses, thor_names)]
        return dict(entries)

    async def lookup_thorname_by_name(self, name: str, forced=False) -> Optional[ThorName]:
        name = name.strip()
        if name in self._known_names:
            return self._known_names[name]

        if not self._thorname_enabled:
            return

        if forced or not (thorname := await self._cache_load_thor_name(name)):
            thorname = await self.call_api_thorname_lookup(name)
            await self._cache_save_thor_name(name, thorname)  # save anyway, even if there is not ThorName!

            if forced and thorname:
                await self._cache_save_name_list(self.get_thor_address_of_thorname(thorname), [thorname.name])

        return thorname

    @staticmethod
    def get_thor_address_of_thorname(thor: ThorName) -> Optional[str]:
        if thor:
            try:
                return next(alias.address for alias in thor.aliases if alias.chain == Chains.THOR)
            except StopIteration:
                pass

    # ---- CACHING stuff ----

    def lookup_name_by_address_local(self, address: str) -> Optional[ThorName]:
        return self._known_address.get(address)

    def _load_preconfigured_names(self):
        name_dic: dict = self.cfg.get_pure('names.preconfig', {})
        for address, label in name_dic.items():
            if address and label:
                self._known_address[address] = ThorName(
                    label, 0, address.encode(),
                    aliases=[
                        ThorNameAlias(Chains.detect_chain(address), address)
                    ]
                )
                self._known_names[label] = address

        self.affiliates = keys_to_lower(self.cfg.get_pure('names.affiliates'))

    def get_affiliate_name(self, affiliate_short: str):
        return self.affiliates.get(affiliate_short.lower())

    @staticmethod
    def _key_thorname_to_addresses(name: str):
        return f'THORName:Entries:{name}'

    @staticmethod
    def _key_address_to_names(address: str):
        return f'THORName:Address-to-Names:{address}'

    async def _cache_save_name_list(self, address: str, names: List[str]):
        await self.db.redis.set(self._key_address_to_names(address),
                                value=json.dumps(names),
                                ex=self._thorname_expire)

    async def _cache_load_name_list(self, address: str) -> List[str]:
        data = await self.db.redis.get(self._key_address_to_names(address))
        return json.loads(data) if data else None

    NO_VALUE = 'no_value'

    async def _cache_save_thor_name(self, name, thorname: ThorName):
        if not name:
            return

        value = thorname.to_json() if thorname else self.NO_VALUE
        await self.db.redis.set(
            self._key_thorname_to_addresses(name),
            value=value,
            ex=self._thorname_expire
        )

    async def _cache_load_thor_name(self, name: str) -> Optional[ThorName]:
        if not name:
            return

        data = await self.db.redis.get(self._key_thorname_to_addresses(name))
        if not data:
            return

        try:
            if data == self.NO_VALUE:
                return data
            else:
                return ThorName().from_json(data)
        except (TypeError, struct.error):
            return

    async def clear_cache_for_name(self, name: str):
        await self.db.redis.delete(self._key_thorname_to_addresses(name))

    async def clear_cache_for_address(self, address: str):
        await self.db.redis.delete(self._key_address_to_names(address))

    # ---- API calls ----

    def _empty_if_error_or_not_found(self, results):
        if results is None or results == self.midgard.ERROR_RESPONSE or results == self.midgard.ERROR_NOT_FOUND:
            return None
        else:
            return results

    async def call_api_thorname_lookup(self, name: str) -> Optional[ThorName]:
        """
        Returns an array of chains and their addresses associated with the given ThorName
        """
        results = await self.midgard.request(f'/v2/thorname/lookup/{name}')
        results = self._empty_if_error_or_not_found(results)
        if results:
            return ThorName(
                name=name,
                expire_block_height=int(results['expire']),
                owner=results['owner'].encode(),
                aliases=[
                    ThorNameAlias(alias['chain'], alias['address']) for alias in results['entries']
                ]
            )

    async def call_api_thorname_reversed_lookup(self, address: str) -> List[str]:
        """
        Returns an array of ThorNames associated with the given address
        """
        results = await self.midgard.request(f'/v2/thorname/rlookup/{address}')
        results = self._empty_if_error_or_not_found(results)
        return results or []

    async def call_api_get_thornames_owned_by_address(self, thor_address: str):
        """
        Returns an array of ThorNames owned by the address.
        The address is not necessarily an associated address for those thornames.
        """
        results = await self.midgard.request(f'/v2/thorname/owner/{thor_address}')
        results = self._empty_if_error_or_not_found(results)
        return results or []


def add_thor_suffix(thor_name: ThorName):
    if thor_name.expire_block_height:
        return f'{thor_name.name}.thor'
    else:
        return thor_name.name
