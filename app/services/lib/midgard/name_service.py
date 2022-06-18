from typing import Optional, List

from proto.thor_types import THORName, THORNameAlias
from services.lib.config import Config
from services.lib.db import DB
from services.lib.midgard.connector import MidgardConnector


class NameService:
    def __init__(self, db: DB, cfg: Config, midgard: MidgardConnector):
        self.db = db
        self.cfg = cfg
        self.midgard = midgard
        self._known_address = {}
        self._load_preconfigured_names()

    async def lookup_name(self, address: str) -> Optional[THORName]:
        if address in self._known_address:
            return self._known_address[address]
        # todo lookup!
        # 1) read thornames from Database
        # 2) if any and not expired => return it
        # 3) if not or expired:
        # 4) use thor_name_reversed_lookup => [names]
        # 5) thor_name_lookup(names[0]) if names else None

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
