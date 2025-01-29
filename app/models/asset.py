import dataclasses
from collections import defaultdict
from copy import copy
from dataclasses import dataclass
from typing import Iterable, Union

from lib.constants import RUNE_DENOM, Chains, NATIVE_RUNE_SYMBOL

ASSET_NORMAL_SEPARATOR = '.'
ASSET_SYNTH_SEPARATOR = '/'
ASSET_TRADE_SEPARATOR = '~'


def is_synthetic(asset: str):
    return ASSET_SYNTH_SEPARATOR in asset


def is_trade_asset(asset: str):
    return ASSET_TRADE_SEPARATOR in asset


def normalize_asset(asset: str):
    asset = asset.replace(ASSET_SYNTH_SEPARATOR, ASSET_NORMAL_SEPARATOR, 1).strip()
    asset = asset.replace(ASSET_TRADE_SEPARATOR, ASSET_NORMAL_SEPARATOR, 1)
    return asset


@dataclass
class Asset:
    chain: str = ''
    name: str = ''
    tag: str = ''
    is_synth: bool = False
    is_virtual: bool = False
    is_trade: bool = False

    @property
    def valid(self):
        return bool(self.chain) and bool(self.name)

    def __post_init__(self):
        if self.chain and not self.name:
            source = self.chain
            a = self.from_string(source)
            self.chain = a.chain
            self.name = a.name
            self.tag = a.tag
            self.is_synth = a.is_synth
            self.is_virtual = a.is_virtual
            self.is_trade = a.is_trade
            # don't forget to copy the rest of fields if you add them!

    @staticmethod
    def get_name_tag(name_and_tag_str):
        components = name_and_tag_str.split('-', maxsplit=2)
        if len(components) == 2:
            return components
        else:
            return name_and_tag_str, ''

    def upper(self):
        asset = copy(self)
        asset.chain = asset.chain.upper()
        asset.name = asset.name.upper()
        asset.tag = asset.tag.upper()
        return asset

    @classmethod
    def from_string(cls, asset: str):
        if isinstance(asset, Asset):
            return asset

        if not isinstance(asset, str):
            raise ValueError('Asset must be a string')

        if asset == RUNE_DENOM:
            return copy(AssetRUNE)

        is_synth, is_trade = False, False
        if is_synthetic(asset):
            is_synth = True
            separator = ASSET_SYNTH_SEPARATOR
        elif is_trade_asset(asset):
            is_trade = True
            separator = ASSET_TRADE_SEPARATOR
        else:
            separator = ASSET_NORMAL_SEPARATOR

        try:
            chain, name_and_tag = asset.split(separator, maxsplit=2)
            name, tag = cls.get_name_tag(name_and_tag)
            chain = str(chain).upper()
            name = str(name).upper()
            tag = str(tag).upper()
            is_virtual = chain == 'THOR' and name != 'RUNE'
            return cls(chain, name, tag, is_synth, is_virtual, is_trade)
        except ValueError:
            # not enough values to unpack. It's a string like "ETH" or "BTC"
            return cls.gas_asset_from_chain(str(asset).upper())

    PILL = '💊'
    TRADE = '🔄'

    @property
    def pretty_str(self):
        pn = self._pretty_name.upper()
        if self.is_synth:
            return f'synth {pn}'
        elif self.is_trade:
            return f'trade {pn}'
        else:
            return pn

    @property
    def _pretty_name(self):
        sep = self.separator_symbol
        str_me = str(self)
        if is_rune(str_me):
            return 'Rune ᚱ'
        elif normalize_asset(str_me) in self.ABBREVIATE_GAS_ASSETS:
            return self.name  # Not ETH.ETH, just ETH
        else:
            return f'{self.chain}{sep}{self.name}'

    @property
    def pretty_str_no_emoji(self):
        return self.pretty_str.replace(self.PILL, '')

    @property
    def shortest(self):
        return f'{self.chain}.{self.name}'

    @property
    def full_name(self):
        if self.valid:
            return f'{self.name}-{self.tag}' if self.tag else self.name
        else:
            return self.name

    @property
    def separator_symbol(self):
        if self.is_trade:
            return ASSET_TRADE_SEPARATOR
        elif self.is_synth:
            return ASSET_SYNTH_SEPARATOR
        else:
            return ASSET_NORMAL_SEPARATOR

    @property
    def to_canonical(self):
        return f'{self.chain}{self.separator_symbol}{self.full_name}'

    @property
    def first_filled_component(self):
        return self.chain or self.name or self.tag

    @property
    def native_pool_name(self):
        return f'{self.chain}.{self.full_name}' if self.valid else self.name

    @property
    def l1_asset(self):
        return dataclasses.replace(self, is_synth=False, is_trade=False, is_virtual=False)

    def __str__(self):
        return self.to_canonical

    @classmethod
    def to_L1_pool_name(cls, asset: str):
        return cls.from_string(asset).native_pool_name

    @property
    def is_gas_asset(self):
        return self.gas_asset_from_chain(self.chain) == self

    SHORT_NAMES = {
        'a': 'AVAX.AVAX',
        'b': 'BTC.BTC',
        'c': 'BCH.BCH',
        'n': 'BNB.BNB',
        's': 'BSC.BNB',
        'd': 'DOGE.DOGE',
        'e': 'ETH.ETH',
        'l': 'LTC.LTC',
        'r': 'THOR.RUNE',
        'f': 'BASE.ETH'
    }

    ABBREVIATE_GAS_ASSETS = {
        'ETH.ETH', 'BTC.BTC', 'LTC.LTC', 'AVAX.AVAX', 'DOGE.DOGE', 'GAIA.ATOM', 'BSC.BNB', 'BCH.BCH',
    }

    GAS_ASSETS = {
        Chains.ATOM: 'ATOM',
        Chains.THOR: 'RUNE',
        Chains.BSC: 'BNB',
        Chains.BASE: 'ETH',
        # to be continued...
    }

    @classmethod
    def gas_asset_from_chain(cls, chain: str):
        chain = chain.upper()
        name = cls.GAS_ASSETS.get(chain, chain)
        return cls(chain, name)


AssetRUNE = Asset.from_string(NATIVE_RUNE_SYMBOL)


def is_rune(asset: Union[Asset, str]):
    if isinstance(asset, Asset):
        asset = str(asset)
    asset = asset.strip()
    return asset.lower() in ('r', RUNE_DENOM) or asset.upper() == NATIVE_RUNE_SYMBOL


def is_ambiguous_asset(asset: Union[str, Asset], among_assets: Iterable[str] = None):
    asset = Asset.from_string(asset)
    if asset.gas_asset_from_chain(asset.chain) != asset:
        return True

    if among_assets is None:
        return False

    ambiguous_tracker = defaultdict(set)
    for a in among_assets:
        name = Asset.from_string(a).name
        ambiguous_tracker[name].add(a)

    return len(ambiguous_tracker.get(asset.name, [])) > 1
