import json
from typing import NamedTuple, List

from lib.constants import Chains


class ThorNameAlias(NamedTuple):
    chain: str
    address: str


class ThorName(NamedTuple):
    name: str
    expire_block_height: int
    owner: str
    aliases: List[ThorNameAlias]

    def to_dict(self):
        d = {
            'name': self.name,
            'expiry': self.expire_block_height,
            'owner': self.owner,
            'aliases': [
                {
                    'chain': alias.chain,
                    'address': alias.address
                }
                for alias in self.aliases
            ]
        }
        return json.dumps(d)

    @classmethod
    def from_json(cls, data_str):
        data = data_str if isinstance(data_str, dict) else json.loads(data_str)
        return ThorName(
            data['name'],
            data['expiry'],
            data['owner'],
            [
                ThorNameAlias(
                    alias['chain'],
                    alias['address']
                )
                for alias in data['aliases']
            ]
        )


def make_virtual_thor_name(address: str, name: str):
    return ThorName(
        name, 0, address,
        aliases=[
            ThorNameAlias(Chains.detect_chain(address), address)
        ]
    )
