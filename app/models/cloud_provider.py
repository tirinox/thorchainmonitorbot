import re
from typing import NamedTuple, Optional, List, Dict, Tuple

import yaml

from lib.path import get_data_path
from models.geo_ip import LocationInfo

CLOUD_PROVIDERS_FILENAME = f'{get_data_path()}/cloud_providers.yaml'

# what a company name ends with: "DigitalOcean, LLC", "MEVSPACE sp. z o.o.", "Leaseweb UK Limited"
_LEGAL_WORDS = {
    'llc', 'l.l.c', 'ltd', 'limited', 'inc', 'incorporated', 'corp', 'corporation', 'co', 'company',
    'gmbh', 'mbh', 'ag', 'kg', 'ug', 'se', 'bv', 'b.v', 'nv', 'n.v', 'sa', 's.a', 'sas', 's.a.s', 'sarl', 's.a.r.l',
    'srl', 's.r.l', 'spa', 's.p.a', 'sro', 's.r.o', 'sp', 'z', 'o.o', 'zoo', 'ehf', 'pty', 'plc', 'uab', 'ou', 'oü',
    'ab', 'a/s', 'aps', 'oy', 'oyj', 'kft', 'doo', 'd.o.o', 'pte', 'lp', 'llp', 'pvt', 'jsc', 'ooo',
    'holdings', 'holding', 'parent',
}


def clean_company_name(name: str) -> str:
    """ "Hostinger International Limited" stays but loses "Limited"; "LUMADOCK LTD" => "Lumadock" """
    words = str(name or '').replace(',', ' ').split()
    while len(words) > 1 and words[-1].lower().strip('.') in _LEGAL_WORDS:
        words.pop()
    name = ' '.join(words).strip(' .-')
    if name.isupper() and len(name) > 4:
        name = name.title()
    return name


class CloudProvider(NamedTuple):
    name: str
    asn: Tuple[int, ...] = ()
    match: Tuple[str, ...] = ()


class CloudProviderDB:
    """Names the owner of an IP address: a known provider from cloud_providers.yaml or the tidied name of its AS"""

    def __init__(self, providers: List[CloudProvider]):
        self.providers = providers
        self._by_asn: Dict[int, CloudProvider] = {}
        self._by_word = []
        for p in providers:
            for asn in p.asn:
                self._by_asn[asn] = p
            for phrase in p.match:
                # the whole word: "ovh" is not found in "Novohost"
                pattern = re.compile(rf'(?<![a-z0-9]){re.escape(phrase.lower())}(?![a-z0-9])')
                self._by_word.append((pattern, p))

    @classmethod
    def from_file(cls, filename=CLOUD_PROVIDERS_FILENAME) -> 'CloudProviderDB':
        with open(filename, 'r') as f:
            data = yaml.safe_load(f) or {}
        return cls([
            CloudProvider(
                name=str(item['name']),
                asn=tuple(int(a) for a in item.get('asn') or ()),
                match=tuple(str(m) for m in item.get('match') or ()),
            )
            for item in data.get('providers') or []
        ])

    _default: Optional['CloudProviderDB'] = None

    @classmethod
    def default(cls) -> 'CloudProviderDB':
        if cls._default is None:
            cls._default = cls.from_file()
        return cls._default

    def find(self, info: Optional[LocationInfo]) -> Optional[CloudProvider]:
        if not info:
            return None
        if provider := self._by_asn.get(info.asn):
            return provider
        # the AS name is the most stable of the three, the org is the least
        for text in (info.as_name, info.org, info.isp):
            text = str(text or '').lower()
            if text:
                for pattern, provider in self._by_word:
                    if pattern.search(text):
                        return provider
        return None

    def name_of(self, info: Optional[LocationInfo]) -> str:
        """An empty string if nothing is known about the owner of the address"""
        if not info:
            return ''
        if provider := self.find(info):
            return provider.name
        return clean_company_name(info.as_name) or clean_company_name(info.org) or clean_company_name(info.isp)
